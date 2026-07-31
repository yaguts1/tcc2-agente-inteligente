"""Triagem: "meus pacientes".

O dashboard de uma ala de 30 leitos e uma tabela de 30 linhas ordenada por
gravidade. A ordenacao esta certa, e nao e ela o problema: a lista e de TODO
MUNDO, logo de NINGUEM. Cada enfermeira le as trinta, decide quais sao suas, e
refaz isso a cada atualizacao da tela — e numa passagem de plantao quem entrou
nem sabe quais leitos assumiu.

DUAS PROPRIEDADES CARREGAM O ARQUIVO, e as duas sao sobre confundir coisas
parecidas:

  1. atribuicao NAO e controle de acesso. Unidade (1.2) fecha o que a pessoa
     nao PODE ver; atribuicao esconde o que ela pode ver e nao precisa agora.
     Trocar um pelo outro transformaria triagem em permissao — ou, pior, o
     contrario: alguem veria outra ala so por ter assumido um leito la;

  2. `apenas_meus` usa o usuario da SESSAO. Aceitar um nome por parametro
     permitiria ler a lista de trabalho de outra pessoa, e num sistema onde a
     lista revela leito e risco isso e acesso a dado clinico por porta lateral.
"""

from datetime import UTC, datetime, timedelta

import pytest

from interface.db_core import connect
from interface.repositories import atribuicoes as repo

BASE = datetime(2026, 6, 1, 8, 0, 0)


@pytest.fixture
def enfermeiras(app_isolado):
    from interface.repositories.users import UserRepository

    r = UserRepository(app_isolado.db_path)
    r.create("ana", "hash", role="staff")
    r.create("bruno", "hash", role="staff")
    return ("ana", "bruno")


@pytest.fixture
def leitos(app_isolado):
    """Tres pacientes internados, cada um com um alerta aberto."""
    iso = BASE.strftime("%Y-%m-%dT%H:%M:%S")
    ms = int(BASE.replace(tzinfo=UTC).timestamp() * 1000)
    with connect(app_isolado.db_path) as conn:
        for i in range(3):
            pid = f"PAC-{i + 1:04d}"
            conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (pid,))
            conn.execute(
                "INSERT INTO paciente_fichas"
                " (paciente_id, nome, perfil, cama_id, created_at, updated_at, unidade_id)"
                " VALUES (?,?,'alto',?,?,?,1)",
                (pid, f"Paciente {i}", f"20{i}-A", iso, iso),
            )
            # Internacao ATIVA: sem ela a ficha nao aparece na listagem (1.1),
            # e o alerta sai sem nome e sem leito.
            conn.execute(
                "INSERT INTO internacoes (paciente_id, admissao_ts, admissao_ms)"
                " VALUES (?,?,?)",
                (pid, iso, ms),
            )
            conn.execute(
                "INSERT INTO alertas (paciente_id, inicio, tipo, perfil, janela_min, status)"
                " VALUES (?,?,'imobilidade','alto',60,'aberto')",
                (pid, (BASE + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S")),
            )
    return ["PAC-0001", "PAC-0002", "PAC-0003"]


# ---------------------------------------------------------------------------
# Atribuicao
# ---------------------------------------------------------------------------


def test_assumir_e_idempotente(app_isolado, enfermeiras, leitos):
    """Tocar duas vezes em "assumir" acontece quando a tela demora e a pessoa
    insiste. Duas atribuicoes ativas fariam a contagem de "meus pacientes"
    mentir."""
    assert repo.assumir(app_isolado.db_path, "PAC-0001", "ana") is True
    assert repo.assumir(app_isolado.db_path, "PAC-0001", "ana") is False

    assert repo.pacientes_de(app_isolado.db_path, "ana") == {"PAC-0001"}
    with connect(app_isolado.db_path) as conn:
        ativas = conn.execute(
            "SELECT COUNT(*) FROM atribuicoes_paciente WHERE liberado_ms IS NULL"
        ).fetchone()[0]
    assert ativas == 1


def test_duas_pessoas_podem_responder_pelo_mesmo_leito(app_isolado, enfermeiras, leitos):
    """Numa transicao de plantao e legitimo — e mostrar so um esconderia a
    passagem, que e justamente o momento em que a informacao vale mais."""
    repo.assumir(app_isolado.db_path, "PAC-0001", "ana")
    repo.assumir(app_isolado.db_path, "PAC-0001", "bruno")

    responsaveis = repo.responsaveis_por(app_isolado.db_path, "PAC-0001")
    assert {r["usuario"] for r in responsaveis} == {"ana", "bruno"}


def test_liberar_preserva_o_historico(app_isolado, enfermeiras, leitos):
    """Encerrar e ESTADO, nao delete — mesmo motivo de `internacoes.alta_ms`.

    Apagar destruiria a evidencia de quem respondia por aquele leito, e e
    exatamente ela que a analise de adesao por enfermeiro (5.1) precisa.
    """
    repo.assumir(app_isolado.db_path, "PAC-0001", "ana")
    repo.liberar(app_isolado.db_path, "PAC-0001", "ana")

    assert repo.pacientes_de(app_isolado.db_path, "ana") == set()
    with connect(app_isolado.db_path) as conn:
        linha = conn.execute(
            "SELECT usuario, liberado_em FROM atribuicoes_paciente"
        ).fetchone()
    assert linha["usuario"] == "ana"
    assert linha["liberado_em"] is not None


def test_reassumir_depois_de_liberar_funciona(app_isolado, enfermeiras, leitos):
    """O indice unico e PARCIAL (`WHERE liberado_ms IS NULL`). Se fosse total,
    a enfermeira que liberasse um leito por engano nao conseguiria retoma-lo —
    e o erro so apareceria no plantao seguinte."""
    repo.assumir(app_isolado.db_path, "PAC-0001", "ana")
    repo.liberar(app_isolado.db_path, "PAC-0001", "ana")

    assert repo.assumir(app_isolado.db_path, "PAC-0001", "ana") is True
    assert repo.pacientes_de(app_isolado.db_path, "ana") == {"PAC-0001"}


def test_liberar_todos_encerra_o_plantao(app_isolado, enfermeiras, leitos):
    """Sem isto, quem sai do turno teria de liberar leito a leito — e nao faria,
    porque ninguem faz. "Meus pacientes" acumularia o hospital inteiro ao longo
    de semanas, ate deixar de significar qualquer coisa."""
    for pid in leitos:
        repo.assumir(app_isolado.db_path, pid, "ana")
    repo.assumir(app_isolado.db_path, "PAC-0001", "bruno")

    assert repo.liberar_todos(app_isolado.db_path, "ana") == 3

    assert repo.pacientes_de(app_isolado.db_path, "ana") == set()
    # Nao pode ter soltado os do colega.
    assert repo.pacientes_de(app_isolado.db_path, "bruno") == {"PAC-0001"}


def test_liberar_o_que_nao_e_seu_nao_faz_nada(app_isolado, enfermeiras, leitos):
    repo.assumir(app_isolado.db_path, "PAC-0001", "ana")

    assert repo.liberar(app_isolado.db_path, "PAC-0001", "bruno") is False
    assert repo.pacientes_de(app_isolado.db_path, "ana") == {"PAC-0001"}


# ---------------------------------------------------------------------------
# O filtro na listagem
# ---------------------------------------------------------------------------


@pytest.fixture
def cliente(app_isolado, cabecalho_auth, monkeypatch):
    from fastapi.testclient import TestClient

    from interface.services import alerts_service

    monkeypatch.setattr(alerts_service, "DB_PATH", app_isolado.db_path)
    return lambda usuario: TestClient(
        app_isolado.app, headers=cabecalho_auth(username=usuario)
    )


def _limpar_cache():
    import asyncio

    from interface.api_shared import api_cache

    asyncio.run(api_cache.clear())


def test_apenas_meus_filtra_pela_atribuicao(app_isolado, enfermeiras, leitos, cliente):
    repo.assumir(app_isolado.db_path, "PAC-0002", "ana")
    _limpar_cache()

    resposta = cliente("ana").get("/api/frontend/alerts?apenas_meus=true")

    assert resposta.status_code == 200, resposta.text
    assert [a["patientId"] for a in resposta.json()] == ["PAC-0002"]


def test_sem_o_filtro_a_lista_continua_completa(app_isolado, enfermeiras, leitos, cliente):
    """A triagem e OPCIONAL. Quem quer a visao da ala inteira — a coordenacao,
    ou quem esta cobrindo o colega — nao pode ser obrigado a assumir leitos."""
    repo.assumir(app_isolado.db_path, "PAC-0002", "ana")
    _limpar_cache()

    resposta = cliente("ana").get("/api/frontend/alerts")

    assert len(resposta.json()) == 3


def test_a_lista_de_uma_pessoa_nao_vaza_para_outra(
    app_isolado, enfermeiras, leitos, cliente
):
    """A CHAVE DE CACHE.

    `unidades` entrou na chave em 1.2 pelo mesmo motivo, e a licao vale igual
    aqui: sem `meus_de` na chave, a lista filtrada de ana serviria do cache para
    bruno, que veria os pacientes DELA como se fossem os dele. Pior que nao ter
    o filtro, porque a tela pareceria correta.
    """
    repo.assumir(app_isolado.db_path, "PAC-0001", "ana")
    repo.assumir(app_isolado.db_path, "PAC-0003", "bruno")
    _limpar_cache()

    de_ana = cliente("ana").get("/api/frontend/alerts?apenas_meus=true").json()
    de_bruno = cliente("bruno").get("/api/frontend/alerts?apenas_meus=true").json()

    assert [a["patientId"] for a in de_ana] == ["PAC-0001"]
    assert [a["patientId"] for a in de_bruno] == ["PAC-0003"]


def test_nao_da_para_pedir_a_lista_de_outra_pessoa(
    app_isolado, enfermeiras, leitos, cliente
):
    """`apenas_meus` usa o usuario da SESSAO, e a rota nao aceita nome nenhum.

    Se aceitasse, a lista de trabalho de alguem seria legivel por qualquer um —
    e ela revela leito e risco, entao seria leitura de dado clinico por porta
    lateral.
    """
    repo.assumir(app_isolado.db_path, "PAC-0001", "ana")
    _limpar_cache()

    # Parametro inventado: o FastAPI o ignora, e a resposta tem de ser a de
    # bruno (vazia), nunca a de ana.
    resposta = cliente("bruno").get(
        "/api/frontend/alerts?apenas_meus=true&usuario=ana&meus_de=ana"
    )

    assert resposta.json() == []


def test_atribuicao_nao_amplia_o_que_a_pessoa_pode_ver(
    app_isolado, enfermeiras, leitos, cliente
):
    """Atribuicao esconde, nunca revela.

    Unidade (1.2) e fronteira de ACESSO; atribuicao e fronteira de ATENCAO. Se
    assumir um leito ampliasse a visibilidade, bastaria assumir um paciente de
    outra ala para ler a ala inteira — triagem viraria escalonamento de
    privilegio.
    """
    from interface.repositories.unidades import criar_unidade

    outra = criar_unidade(app_isolado.db_path, "Ala B")
    with connect(app_isolado.db_path) as conn:
        conn.execute(
            "UPDATE paciente_fichas SET unidade_id = ? WHERE paciente_id = 'PAC-0003'",
            (outra["id"],),
        )
    repo.assumir(app_isolado.db_path, "PAC-0003", "ana")
    _limpar_cache()

    import asyncio

    from interface.services.alerts_service import listar_alertas_frontend

    # `unidades={1}` = ana so enxerga a Ala A. PAC-0003 esta na Ala B.
    visiveis = asyncio.run(
        listar_alertas_frontend(unidades={1}, meus_de="ana")
    )

    assert [a["patientId"] for a in visiveis] == []
