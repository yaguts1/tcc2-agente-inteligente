"""A variavel de desfecho, que nao existia.

O sistema media adesao ao reposicionamento e NUNCA registrava se a lesao
aconteceu. Sem entidade de lesao — com estagio, sitio, data e origem — a
correlacao que o projeto existe para demonstrar (adesao ao protocolo vs.
incidencia de LPP) nao era computavel NEM EM PRINCIPIO a partir do banco:
media-se o processo e ignorava-se o resultado.

Tres coisas que estes testes travam, e que sao onde o indicador erra facil:

  * `origem` separa incidencia de prevalencia. Lesao que o paciente TROUXE nao e
    falha do cuidado desta unidade. Somar as duas pune quem recebe paciente
    grave de outro servico — e e esse numero que faz uma equipe deixar de
    registrar lesao;

  * o denominador e paciente-DIA, recortado NA JANELA. Sem o recorte, uma
    internacao de seis meses contaria inteira numa janela de 30 dias e o
    denominador inflaria a ponto de zerar a incidencia;

  * a evolucao e historico, nao estado. "Estagio 2 que cicatrizou em 6 dias" e
    "estagio 2 que virou 4" nao sao o mesmo desfecho.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from interface.db_core import connect
from interface.repositories import lesoes as repo
from interface.repositories.pacientes import PatientRepository
from interface.tempo import agora_utc_naive

UNIDADE_A = 1


@pytest.fixture
def db(app_isolado):
    return app_isolado.db_path


@pytest.fixture
def pacientes(db):
    return PatientRepository(db)


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


@pytest.fixture
def ana(pacientes):
    return pacientes.create(nome="Ana", perfil="alto", cama_id="201-A")["paciente_id"]


def _periodo_de_leito(db, paciente_id, dias, cama="201-A", unidade=UNIDADE_A):
    """Um periodo fechado de `dias`, terminando agora — o denominador."""
    fim = agora_utc_naive()
    inicio = fim - timedelta(days=dias)
    with connect(db) as conn:
        conn.execute("DELETE FROM paciente_cama_history WHERE paciente_id = ?", (paciente_id,))
        conn.execute(
            "INSERT INTO paciente_cama_history"
            " (paciente_id, cama_id, start_ts, start_ms, end_ts, end_ms, unidade_id)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                paciente_id, cama,
                inicio.strftime("%Y-%m-%dT%H:%M:%S"), int(inicio.timestamp() * 1000),
                fim.strftime("%Y-%m-%dT%H:%M:%S"), int(fim.timestamp() * 1000),
                unidade,
            ),
        )


# ------------------------------------------------------------------ registro


def test_registrar_cria_lesao_com_a_primeira_avaliacao(db, ana):
    """As duas na mesma transacao: uma lesao sem avaliacao nao tem estagio, e
    estagio e o que a torna comparavel com qualquer outra."""
    lesao = repo.registrar(
        db, ana, sitio="sacro", origem="adquirida", estagio="estagio_2", usuario="enf.ana"
    )

    assert lesao["sitio"] == "sacro"
    assert lesao["estagio_atual"] == "estagio_2"
    assert lesao["estagio_inicial"] == "estagio_2"
    assert lesao["avaliacoes"] == 1


def test_lesao_e_amarrada_a_internacao_aberta(db, ana):
    """Sem o vinculo, uma lesao de internacao anterior contaria na atual e o
    denominador nao casaria com o numerador."""
    lesao = repo.registrar(db, ana, sitio="sacro", origem="adquirida", estagio="estagio_1")

    assert lesao["internacao_id"] is not None


@pytest.mark.parametrize(
    "campo,valor",
    [("sitio", "joelho"), ("origem", "talvez"), ("estagio", "estagio_9")],
)
def test_vocabulario_fora_da_lista_e_recusado(db, ana, campo, valor):
    kwargs = dict(sitio="sacro", origem="adquirida", estagio="estagio_2")
    kwargs[campo] = valor

    with pytest.raises(ValueError):
        repo.registrar(db, ana, **kwargs)


def test_paciente_inexistente_e_recusado(db):
    with pytest.raises(LookupError):
        repo.registrar(db, "PAC-NAO-EXISTE", sitio="sacro", origem="adquirida", estagio="estagio_1")


# ------------------------------------------------------------------ evolucao


def test_avaliar_acrescenta_sem_apagar_a_anterior(db, ana):
    """A trajetoria E o dado clinico."""
    lesao = repo.registrar(db, ana, sitio="sacro", origem="adquirida", estagio="estagio_2")

    repo.avaliar(db, lesao["id"], estagio="estagio_3", usuario="enf.bruno")
    atual = repo.avaliar(db, lesao["id"], estagio="estagio_4", usuario="enf.bruno")

    assert atual["estagio_inicial"] == "estagio_2", "o estagio de entrada foi perdido"
    assert atual["estagio_atual"] == "estagio_4"
    assert [a["estagio"] for a in atual["historico"]] == [
        "estagio_2", "estagio_3", "estagio_4",
    ]


def test_estagio_atual_e_derivado_e_nao_duplicado(db, ana):
    """Duas fontes para o mesmo fato divergem, e a que divergiria e a que
    alimenta o indicador."""
    lesao = repo.registrar(db, ana, sitio="sacro", origem="adquirida", estagio="estagio_2")

    with connect(db) as conn:
        colunas = [r[1] for r in conn.execute("PRAGMA table_info(lesoes)")]

    assert "estagio" not in colunas
    assert "estagio_atual" not in colunas
    assert repo.obter(db, lesao["id"])["estagio_atual"] == "estagio_2"


def test_fechar_registra_o_desfecho(db, ana):
    lesao = repo.registrar(db, ana, sitio="sacro", origem="adquirida", estagio="estagio_2")

    fechada = repo.fechar(db, lesao["id"], "cicatrizada", usuario="enf.ana")

    assert fechada["desfecho"] == "cicatrizada"
    assert fechada["fechada_ms"] is not None


def test_fechar_duas_vezes_e_recusado(db, ana):
    lesao = repo.registrar(db, ana, sitio="sacro", origem="adquirida", estagio="estagio_2")
    repo.fechar(db, lesao["id"], "cicatrizada")

    with pytest.raises(LookupError):
        repo.fechar(db, lesao["id"], "obito")


# ------------------------------------------------------------------ indicador


def test_incidencia_conta_so_o_que_foi_adquirido(db, pacientes, ana):
    """O ponto inteiro da coluna `origem`.

    Lesao que o paciente trouxe e prevalencia na admissao, nao resultado do
    cuidado prestado aqui.
    """
    bruno = pacientes.create(nome="Bruno", perfil="alto", cama_id="202-B")["paciente_id"]
    _periodo_de_leito(db, ana, dias=10)
    _periodo_de_leito(db, bruno, dias=10, cama="202-B")

    repo.registrar(db, ana, sitio="sacro", origem="adquirida", estagio="estagio_2")
    repo.registrar(
        db, bruno, sitio="calcaneo_esquerdo", origem="presente_na_admissao", estagio="estagio_3"
    )

    ind = repo.indicadores(db, horas=24 * 30)

    assert ind["lesoes_adquiridas"] == 1
    assert ind["lesoes_presentes_na_admissao"] == 1
    # 1 adquirida / 20 paciente-dia * 1000 = 50
    assert ind["pacientes_dia"] == pytest.approx(20, abs=0.5)
    assert ind["incidencia_por_1000_pacientes_dia"] == pytest.approx(50, abs=2)


def test_denominador_e_recortado_na_janela(db, ana):
    """Sem o recorte, uma internacao longa contaria inteira numa janela curta e
    o denominador inflaria a ponto de zerar a incidencia."""
    _periodo_de_leito(db, ana, dias=180)

    janela_curta = repo.indicadores(db, horas=24 * 30)

    assert janela_curta["pacientes_dia"] == pytest.approx(30, abs=1), (
        "os 180 dias entraram inteiros numa janela de 30"
    )


def test_sem_paciente_dia_a_incidencia_e_nula_e_nao_zero(db):
    """Zero seria o melhor resultado possivel; "nao ha denominador" e outra
    coisa."""
    ind = repo.indicadores(db, horas=24)

    assert ind["pacientes_dia"] == 0
    assert ind["incidencia_por_1000_pacientes_dia"] is None


def test_indicador_respeita_o_escopo_de_unidade(db, pacientes, ana):
    from interface.repositories.unidades import criar_unidade

    outra = criar_unidade(db, "Ala Sul")["id"]
    bruno = pacientes.create(
        nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=outra
    )["paciente_id"]
    _periodo_de_leito(db, ana, dias=10)
    _periodo_de_leito(db, bruno, dias=10, cama="305-B", unidade=outra)
    repo.registrar(db, ana, sitio="sacro", origem="adquirida", estagio="estagio_2")
    repo.registrar(db, bruno, sitio="sacro", origem="adquirida", estagio="estagio_2")

    so_a = repo.indicadores(db, horas=24 * 30, unidades={UNIDADE_A})

    assert so_a["lesoes_adquiridas"] == 1
    assert so_a["pacientes_dia"] == pytest.approx(10, abs=0.5)


# ------------------------------------------------------------------ endpoints


def test_vocabulario_vem_do_servidor(client, cabecalho_auth):
    """Uma copia da lista no JavaScript e o comeco de duas listas divergentes —
    ja aconteceu neste projeto com o intervalo por perfil de risco (motor
    60/90/120 min, tela 2/3/4 h, o dobro)."""
    corpo = client.get("/api/lesoes/vocabulario", headers=cabecalho_auth()).json()

    assert "sacro" in corpo["sitios"]
    assert set(corpo["origens"]) == {"presente_na_admissao", "adquirida"}
    assert "estagio_4" in corpo["estagios"]


def test_rota_de_vocabulario_nao_e_engolida_pela_de_id(client, cabecalho_auth):
    """`/lesoes/vocabulario` casaria com `/lesoes/{lesao_id}` se viesse depois —
    o FastAPI resolve na ordem de registro, e o sintoma seria 422 tentando
    converter "vocabulario" em int. Mesmo problema que `/agenda/check` e
    `/usuarios/eu/senha` ja tiveram."""
    for caminho in ("/api/lesoes/vocabulario", "/api/lesoes/indicadores"):
        assert client.get(caminho, headers=cabecalho_auth()).status_code == 200, caminho


def test_registrar_pela_api(client, cabecalho_auth, ana, db):
    resposta = client.post(
        f"/api/pacientes/{ana}/lesoes",
        json={"sitio": "sacro", "origem": "adquirida", "estagio": "estagio_2"},
        headers=cabecalho_auth(username="enf.ana"),
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["identificada_por"] == "enf.ana"


def test_origem_e_obrigatoria_na_api(client, cabecalho_auth, ana):
    """Um default decidiria por quem registra a pergunta que separa o que pode
    ser atribuido ao cuidado do que nao pode."""
    resposta = client.post(
        f"/api/pacientes/{ana}/lesoes",
        json={"sitio": "sacro", "estagio": "estagio_2"},
        headers=cabecalho_auth(),
    )

    assert resposta.status_code == 422


def test_lesoes_exigem_sessao(client, ana):
    assert client.get(f"/api/pacientes/{ana}/lesoes").status_code == 401
    assert client.get("/api/lesoes/indicadores").status_code == 401
    assert client.post(f"/api/pacientes/{ana}/lesoes", json={}).status_code == 401


def test_evolucao_pela_api(client, cabecalho_auth, ana):
    cab = cabecalho_auth(username="enf.ana")
    criada = client.post(
        f"/api/pacientes/{ana}/lesoes",
        json={"sitio": "sacro", "origem": "adquirida", "estagio": "estagio_2"},
        headers=cab,
    ).json()

    resposta = client.post(
        f"/api/lesoes/{criada['id']}/avaliacoes",
        json={"estagio": "estagio_3", "comprimento_cm": 4.5},
        headers=cab,
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["estagio_atual"] == "estagio_3"
    assert resposta.json()["estagio_inicial"] == "estagio_2"
