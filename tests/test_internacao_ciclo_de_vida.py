"""Internacao: o substantivo que faltava no dominio.

Ate aqui existia CRUD de ficha e mais nada. Tres consequencias, todas
verificadas contra o codigo antes de virar teste:

  1. DAR ALTA ERA `delete()`, que apaga — nas palavras do proprio docstring —
     "TODO o rastro clinico": alertas, grade, eventos, timeline e historico de
     leito. A operacao mais rotineira de uma ala destruia exatamente a evidencia
     que acreditacao (ONA/JCI) e LGPD Art. 37 exigem guardar.

  2. MUDANCA DE LEITO era efeito colateral de editar um campo de formulario. O
     estado do motor e por PACIENTE, nao por leito, e nada o zerava: o intervalo
     da transferencia — em que o paciente foi erguido para a maca, levado pelo
     corredor e reacomodado, o momento de maior alivio de pressao do dia dele —
     era lido como UMA corrida continua de imobilidade.

  3. TROCA DE LEITOS entre dois pacientes era impossivel: qualquer sequencia de
     duas edicoes passa por um estado em que um leito tem dois ocupantes, e o
     indice unico parcial recusa. E rotina numa ala.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from interface.db_core import connect
from interface.repositories.pacientes import JaTeveAlta, PatientRepository


@pytest.fixture
def repo(app_isolado):
    return PatientRepository(app_isolado.db_path)


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


def _criar(repo, nome="Ana", cama="201-A", perfil="alto"):
    return repo.create(nome=nome, perfil=perfil, cama_id=cama, registrado_por="tester")


def _gravar_estado_do_motor(db, paciente_id):
    """Estado persistido do decisor, no schema real de `estado_incremental`.

    A tabela e criada sob demanda pelo processador, com
    (paciente_id, estado_json, atualizado_em) — inventar a forma dela aqui faria
    o teste passar contra um schema que nao existe.
    """
    with connect(db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS estado_incremental ("
            " paciente_id TEXT PRIMARY KEY, estado_json TEXT NOT NULL,"
            " atualizado_em TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO estado_incremental VALUES (?, ?, ?)",
            (paciente_id, '{"run_postura": "supino"}', "2026-01-01T00:00:00"),
        )


def _linhas(db, sql, *args):
    with connect(db) as conn:
        return [dict(linha) for linha in conn.execute(sql, args)]


# ---------------------------------------------------------------- admissao


def test_cadastrar_paciente_abre_internacao(repo, app_isolado):
    """Neste sistema nao existe paciente que exista sem estar internado."""
    paciente = _criar(repo)

    episodios = _linhas(
        app_isolado.db_path,
        "SELECT paciente_id, alta_ms, admitido_por FROM internacoes WHERE paciente_id = ?",
        paciente["paciente_id"],
    )
    assert len(episodios) == 1
    assert episodios[0]["alta_ms"] is None, "a internacao nasceu ja encerrada"
    assert episodios[0]["admitido_por"] == "tester"


def test_um_paciente_nao_pode_ter_duas_internacoes_abertas(repo, app_isolado):
    """Garantido pelo indice unico parcial: com dois episodios abertos, nenhuma
    consulta saberia qual e o corrente."""
    paciente = _criar(repo)

    with pytest.raises(sqlite3.IntegrityError):
        with connect(app_isolado.db_path) as conn:
            conn.execute(
                "INSERT INTO internacoes (paciente_id, admissao_ts, admissao_ms)"
                " VALUES (?, '2026-01-01T00:00:00', 0)",
                (paciente["paciente_id"],),
            )


def test_ficha_minima_tambem_abre_internacao(repo):
    """A outra porta de entrada de paciente: import de alertas (routers/admin).

    Sem episodio, esse paciente ficaria impossivel de transferir ou de receber
    alta — as duas exigem internacao aberta e responderiam 409 para sempre, sem
    pista nenhuma de que a causa foi a porta por onde ele entrou.
    """
    repo.ensure_minimal_ficha("PAC-9001", nome="Importado", perfil="alto", cama_id="401-A")

    assert repo.internacao_aberta("PAC-9001") is not None
    repo.dar_alta("PAC-9001")  # nao pode levantar


# ---------------------------------------------------------------- alta


def test_alta_preserva_o_historico_clinico(repo, app_isolado):
    """O ponto inteiro desta mudanca."""
    paciente = _criar(repo)
    pid = paciente["paciente_id"]
    with connect(app_isolado.db_path) as conn:
        conn.execute(
            "INSERT INTO alertas (paciente_id, inicio, tipo, perfil, janela_min, status)"
            " VALUES (?, '2026-01-01T08:00:00', 'imobilidade', 'alto', 60, 'fechado')",
            (pid,),
        )

    repo.dar_alta(pid, motivo="melhora clinica", usuario="enfermeira.ana")

    assert _linhas(app_isolado.db_path, "SELECT 1 FROM alertas WHERE paciente_id = ?", pid), (
        "a alta apagou o alerta — era exatamente o que o delete fazia"
    )
    assert _linhas(app_isolado.db_path, "SELECT 1 FROM paciente_fichas WHERE paciente_id = ?", pid)


def test_alta_registra_motivo_autor_e_permanencia(repo):
    paciente = _criar(repo)

    resultado = repo.dar_alta(
        paciente["paciente_id"], motivo="alta a pedido", usuario="enfermeira.ana"
    )

    assert resultado["permanencia_horas"] >= 0
    episodio = repo.internacao_aberta(paciente["paciente_id"])
    assert episodio is None, "a internacao continuou aberta depois da alta"


def test_alta_libera_o_leito_para_o_proximo(repo):
    """Sem isso o indice unico parcial de `cama_id` recusaria o proximo ocupante."""
    saindo = _criar(repo, nome="Ana", cama="201-A")

    repo.dar_alta(saindo["paciente_id"])

    entrando = _criar(repo, nome="Bruno", cama="201-A")
    assert entrando["cama_id"] == "201-A"


def test_alta_desvincula_o_device(repo, app_isolado):
    """Senao a leitura do sensor do leito continuaria caindo no prontuario de
    quem ja foi embora."""
    paciente = _criar(repo)
    pid = paciente["paciente_id"]
    with connect(app_isolado.db_path) as conn:
        conn.execute(
            "INSERT INTO device_assignments (device_id, cama_id, paciente_id, start_ts, start_ms)"
            " VALUES ('dev-1', '201-A', ?, '2026-01-01T00:00:00', 0)",
            (pid,),
        )

    repo.dar_alta(pid)

    abertos = _linhas(
        app_isolado.db_path,
        "SELECT 1 FROM device_assignments WHERE paciente_id = ? AND end_ms IS NULL",
        pid,
    )
    assert abertos == [], "o device seguiu vinculado a um paciente que teve alta"


def test_alta_duas_vezes_e_recusada(repo):
    paciente = _criar(repo)
    repo.dar_alta(paciente["paciente_id"])

    with pytest.raises(JaTeveAlta):
        repo.dar_alta(paciente["paciente_id"])


# ---------------------------------------------------------------- transferencia


def test_transferencia_fecha_o_periodo_do_leito_antigo(repo, app_isolado):
    paciente = _criar(repo, cama="201-A")
    pid = paciente["paciente_id"]

    repo.transferir(pid, "305-B", usuario="enfermeira.ana")

    periodos = _linhas(
        app_isolado.db_path,
        "SELECT cama_id, end_ms FROM paciente_cama_history WHERE paciente_id = ?"
        " ORDER BY start_ms",
        pid,
    )
    assert [p["cama_id"] for p in periodos] == ["201-A", "305-B"]
    assert periodos[0]["end_ms"] is not None, "o periodo do leito antigo ficou aberto"
    assert periodos[1]["end_ms"] is None


def test_transferencia_zera_o_estado_do_motor(repo, app_isolado):
    """A transferencia E um reposicionamento: ser erguido para a maca e alivio
    de pressao real. Sem zerar, o motor le o intervalo como corrida continua e
    credita o paciente com zero movimento no momento de maior movimento do dia.
    """
    paciente = _criar(repo)
    pid = paciente["paciente_id"]
    _gravar_estado_do_motor(app_isolado.db_path, pid)

    repo.transferir(pid, "305-B")

    restante = _linhas(
        app_isolado.db_path, "SELECT 1 FROM estado_incremental WHERE paciente_id = ?", pid
    )
    assert restante == [], "o paciente levou a corrida do leito antigo para o novo"


def test_transferencia_para_leito_ocupado_e_recusada(repo):
    _criar(repo, nome="Ana", cama="201-A")
    bruno = _criar(repo, nome="Bruno", cama="305-B")

    with pytest.raises(ValueError):
        repo.transferir(bruno["paciente_id"], "201-A")


def test_transferencia_de_quem_teve_alta_e_recusada(repo):
    paciente = _criar(repo)
    repo.dar_alta(paciente["paciente_id"])

    with pytest.raises(JaTeveAlta):
        repo.transferir(paciente["paciente_id"], "305-B")


# ---------------------------------------------------------------- troca


def test_troca_de_leitos_entre_dois_pacientes(repo):
    """Rotina numa ala, e impossivel antes: qualquer ordem de duas edicoes passa
    por um leito com dois ocupantes."""
    ana = _criar(repo, nome="Ana", cama="201-A")
    bruno = _criar(repo, nome="Bruno", cama="305-B")

    repo.trocar_leitos(ana["paciente_id"], bruno["paciente_id"], usuario="enfermeira.ana")

    assert repo.get_by_id(ana["paciente_id"])["cama_id"] == "305-B"
    assert repo.get_by_id(bruno["paciente_id"])["cama_id"] == "201-A"


def test_troca_registra_periodo_de_leito_para_os_dois(repo, app_isolado):
    ana = _criar(repo, nome="Ana", cama="201-A")
    bruno = _criar(repo, nome="Bruno", cama="305-B")

    repo.trocar_leitos(ana["paciente_id"], bruno["paciente_id"])

    for pid, esperado in ((ana["paciente_id"], "305-B"), (bruno["paciente_id"], "201-A")):
        atual = _linhas(
            app_isolado.db_path,
            "SELECT cama_id FROM paciente_cama_history"
            " WHERE paciente_id = ? AND end_ms IS NULL",
            pid,
        )
        assert [a["cama_id"] for a in atual] == [esperado]


def test_troca_com_paciente_sem_leito_e_recusada(repo):
    ana = _criar(repo, nome="Ana", cama="201-A")
    sem_leito = _criar(repo, nome="Bruno", cama=None)

    with pytest.raises(ValueError):
        repo.trocar_leitos(ana["paciente_id"], sem_leito["paciente_id"])


def test_troca_de_um_paciente_com_ele_mesmo_e_recusada(repo):
    ana = _criar(repo, nome="Ana", cama="201-A")

    with pytest.raises(ValueError):
        repo.trocar_leitos(ana["paciente_id"], ana["paciente_id"])


# ---------------------------------------------------------------- delete


def test_delete_leva_o_estado_do_motor_junto(repo, app_isolado):
    """Os IDs sao gerados por "maior existente + 1": apagar PAC-0007 faz o
    proximo paciente se chamar PAC-0007 e HERDAR `baseline_postura` e
    `cooldown_ate` de um estranho. O sintoma seria um paciente novo nascendo em
    cooldown, sem alerta nenhum e sem nada explicando.
    """
    paciente = _criar(repo)
    pid = paciente["paciente_id"]
    _gravar_estado_do_motor(app_isolado.db_path, pid)

    repo.delete(pid)

    assert _linhas(
        app_isolado.db_path, "SELECT 1 FROM estado_incremental WHERE paciente_id = ?", pid
    ) == []


# ---------------------------------------------------------------- endpoints


def test_endpoint_de_alta(client, cabecalho_auth, repo):
    paciente = _criar(repo)

    resposta = client.post(
        f"/api/pacientes/{paciente['paciente_id']}/alta",
        json={"motivo": "melhora clinica"},
        headers=cabecalho_auth(username="enfermeira.ana"),
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["ok"] is True
    assert repo.internacao_aberta(paciente["paciente_id"]) is None


def test_endpoint_de_alta_exige_sessao(client, repo):
    paciente = _criar(repo)

    resposta = client.post(f"/api/pacientes/{paciente['paciente_id']}/alta", json={})

    assert resposta.status_code == 401


def test_endpoint_de_alta_repetida_devolve_409(client, cabecalho_auth, repo):
    paciente = _criar(repo)
    cabecalho = cabecalho_auth()
    client.post(f"/api/pacientes/{paciente['paciente_id']}/alta", json={}, headers=cabecalho)

    resposta = client.post(
        f"/api/pacientes/{paciente['paciente_id']}/alta", json={}, headers=cabecalho
    )

    assert resposta.status_code == 409
    assert resposta.json()["detail"]["code"] == "sem_internacao_aberta"


def test_endpoint_de_transferencia(client, cabecalho_auth, repo):
    paciente = _criar(repo, cama="201-A")

    resposta = client.post(
        f"/api/pacientes/{paciente['paciente_id']}/transferencia",
        json={"room": "305", "bed": "B"},
        headers=cabecalho_auth(),
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["cama_anterior"] == "201-A"
    assert repo.get_by_id(paciente["paciente_id"])["cama_id"] == "305-B"


def test_endpoint_de_troca_de_leitos(client, cabecalho_auth, repo):
    ana = _criar(repo, nome="Ana", cama="201-A")
    bruno = _criar(repo, nome="Bruno", cama="305-B")

    resposta = client.post(
        "/api/pacientes/troca-de-leitos",
        json={"pacienteA": ana["paciente_id"], "pacienteB": bruno["paciente_id"]},
        headers=cabecalho_auth(),
    )

    assert resposta.status_code == 200, resposta.text
    assert repo.get_by_id(ana["paciente_id"])["cama_id"] == "305-B"
