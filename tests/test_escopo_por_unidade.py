"""Escopo por unidade: uma ala nao pode ver (nem acordar) a outra.

O sistema nao tinha nenhum conceito organizacional. Um grep por
unidade/ala/setor/enfermaria/turno/equipe em interface/, migrations/, nucleo/ e
frontend/src so achava prosa em comentario. O que existia era `cama_id`, texto
livre, UNICO EM TODA A INSTALACAO.

Este arquivo cobre o que quebrava com duas alas:

  * colisao de "Leito 12" no banco, recusando a segunda admissao e citando na
    mensagem de erro um paciente de outro predio;
  * toda enfermeira lendo o dado clinico de todo paciente — que a trilha de
    auditoria registra fielmente, transformando-a de defesa em prova;
  * `/stats` mediando as duas alas num numero so.

E cobre a armadilha central da implementacao: `None` (admin, ve tudo) e `set()`
(sem unidade nenhuma, nao ve nada) sao coisas OPOSTAS, e em Python `if not x:`
trata as duas igual. Confundi-las devolve o hospital inteiro exatamente para
quem nao pode ver nada.
"""

import pytest
from fastapi.testclient import TestClient

from interface.db_core import connect
from interface.repositories.pacientes import PatientRepository
from interface.repositories.unidades import (
    criar_unidade,
    definir_unidades_do_usuario,
    filtro_sql,
    unidades_do_usuario,
)
from interface.tempo import agora_utc_naive

UNIDADE_A = 1  # "Unidade Principal", criada pela migration


@pytest.fixture
def repo(app_isolado):
    return PatientRepository(app_isolado.db_path)


@pytest.fixture
def unidade_b(app_isolado):
    return criar_unidade(app_isolado.db_path, "Ala Sul")["id"]


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


def _abrir_alerta(db, paciente_id, minutos_atras=90):
    inicio = (agora_utc_naive() - __import__("datetime").timedelta(minutes=minutos_atras)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO alertas (paciente_id, inicio, tipo, perfil, janela_min, status)"
            " VALUES (?, ?, 'imobilidade', 'alto', 60, 'aberto')",
            (paciente_id, inicio),
        )


# ------------------------------------------------------- colisao de leito


def test_mesmo_leito_pode_existir_em_duas_alas(repo, unidade_b):
    """O caso que travava a instalacao em duas alas.

    `_assert_cama_disponivel` era global: a segunda admissao era recusada com
    "Cama '12' ja esta atribuida ao paciente PAC-0001" — um paciente de outro
    predio, cujo ID o operador nem tinha por que conhecer.
    """
    repo.create(nome="Ana", perfil="alto", cama_id="12", unidade_id=UNIDADE_A)

    bruno = repo.create(nome="Bruno", perfil="alto", cama_id="12", unidade_id=unidade_b)

    assert bruno["cama_id"] == "12"
    assert bruno["unidade_id"] == unidade_b


def test_dentro_da_mesma_ala_o_leito_continua_exclusivo(repo):
    repo.create(nome="Ana", perfil="alto", cama_id="12", unidade_id=UNIDADE_A)

    with pytest.raises(ValueError):
        repo.create(nome="Bruno", perfil="alto", cama_id="12", unidade_id=UNIDADE_A)


# ------------------------------------------------------- a armadilha None vs set()


def test_none_e_conjunto_vazio_sao_opostos():
    """`None` = ve tudo; `set()` = nao ve nada. `if not x:` trata igual."""
    assert filtro_sql(None) == ("", [])

    condicao, params = filtro_sql(set())
    assert condicao.strip() == "AND 1 = 0", "conjunto vazio virou 'sem filtro'"
    assert params == []

    condicao, params = filtro_sql({3, 1})
    assert "IN (?,?)" in condicao
    assert params == [1, 3]


def test_staff_sem_unidade_nao_ve_nada(repo, app_isolado):
    """Deny by default: esquecer de vincular nao pode virar vazamento."""
    repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)

    visiveis = repo.list_all(unidades=set())

    assert visiveis == []


def test_admin_ve_todas_as_unidades(repo, unidade_b, app_isolado):
    repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    repo.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=unidade_b)

    from interface.repositories.users import UserRepository

    UserRepository(app_isolado.db_path).create("chefe", "hash", role="admin")

    assert unidades_do_usuario(app_isolado.db_path, "chefe", "admin") is None
    assert len(repo.list_all(unidades=None)) == 2


# ------------------------------------------------------- escopo nas listagens


def test_listagem_de_pacientes_respeita_a_unidade(repo, unidade_b):
    repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    repo.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=unidade_b)

    somente_a = repo.list_all(unidades={UNIDADE_A})

    assert [f["nome"] for f in somente_a] == ["Ana"]


def test_paciente_com_alta_sai_da_lista_da_ala(repo):
    """Depois que alta virou estado, a lista encheria de quem ja foi embora."""
    ana = repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    repo.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=UNIDADE_A)
    repo.dar_alta(ana["paciente_id"])

    assert [f["nome"] for f in repo.list_all()] == ["Bruno"]
    assert len(repo.list_all(incluir_alta=True)) == 2, (
        "o historico precisa continuar acessivel sob demanda"
    )


# ------------------------------------------------------- escopo ponta a ponta


def _usuario_da_unidade(app_isolado, cabecalho_auth, username, unidades):
    cabecalho = cabecalho_auth(username=username, role="staff")
    definir_unidades_do_usuario(app_isolado.db_path, username, unidades)
    return cabecalho


def test_alertas_de_outra_ala_nao_aparecem(client, app_isolado, cabecalho_auth, repo, unidade_b):
    ana = repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    bruno = repo.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=unidade_b)
    _abrir_alerta(app_isolado.db_path, ana["paciente_id"])
    _abrir_alerta(app_isolado.db_path, bruno["paciente_id"])

    cabecalho = _usuario_da_unidade(app_isolado, cabecalho_auth, "enf.a", [UNIDADE_A])
    alertas = client.get("/api/frontend/alerts", headers=cabecalho).json()

    nomes = {a["patientName"] for a in alertas}
    assert nomes == {"Ana"}, f"vazou alerta de outra ala: {nomes}"


def test_cache_nao_serve_a_pagina_de_uma_ala_para_a_outra(
    client, app_isolado, cabecalho_auth, repo, unidade_b
):
    """A falha mais silenciosa possivel deste bloco.

    A listagem tem cache de 30s por chave. Se a unidade nao entrar na chave, a
    ala A carrega, e a proxima requisicao — de outra ala — recebe a pagina dela
    pronta do cache. A tela pareceria correta, o que e pior que um erro.
    """
    ana = repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    bruno = repo.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=unidade_b)
    _abrir_alerta(app_isolado.db_path, ana["paciente_id"])
    _abrir_alerta(app_isolado.db_path, bruno["paciente_id"])

    cab_a = _usuario_da_unidade(app_isolado, cabecalho_auth, "enf.a", [UNIDADE_A])
    cab_b = _usuario_da_unidade(app_isolado, cabecalho_auth, "enf.b", [unidade_b])

    primeira = client.get("/api/frontend/alerts", headers=cab_a).json()
    segunda = client.get("/api/frontend/alerts", headers=cab_b).json()

    assert {a["patientName"] for a in primeira} == {"Ana"}
    assert {a["patientName"] for a in segunda} == {"Bruno"}, (
        "a ala B recebeu do cache a pagina da ala A"
    )


def test_stats_nao_media_as_duas_alas(client, app_isolado, cabecalho_auth, repo, unidade_b):
    repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    repo.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=unidade_b)
    repo.create(nome="Carla", perfil="alto", cama_id="306-B", unidade_id=unidade_b)

    cab_a = _usuario_da_unidade(app_isolado, cabecalho_auth, "enf.a", [UNIDADE_A])
    stats = client.get("/api/stats", headers=cab_a).json()

    assert stats["totalPatients"] == 1, (
        f"a contagem incluiu pacientes de outra ala: {stats['totalPatients']}"
    )


def test_monitoramento_nao_nomeia_leitos_de_outra_ala(
    client, app_isolado, cabecalho_auth, repo, unidade_b
):
    """O painel NOMEIA os leitos sem leitura — sem escopo, expoe a ala vizinha."""
    repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    repo.create(nome="Bruno", perfil="alto", cama_id="305-B", unidade_id=unidade_b)

    cab_a = _usuario_da_unidade(app_isolado, cabecalho_auth, "enf.a", [UNIDADE_A])
    corpo = client.get("/api/monitoramento", headers=cab_a).json()

    texto = str(corpo)
    assert "Bruno" not in texto and "305-B" not in texto, (
        "o painel de monitoramento vazou leito/paciente de outra ala"
    )


def test_usuario_sem_unidade_ve_tela_vazia_e_nao_o_hospital(
    client, app_isolado, cabecalho_auth, repo
):
    repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)

    cabecalho = _usuario_da_unidade(app_isolado, cabecalho_auth, "novato", [])
    pacientes = client.get("/api/pacientes", headers=cabecalho).json()
    alertas = client.get("/api/frontend/alerts", headers=cabecalho).json()

    assert pacientes == []
    assert alertas == []


# ------------------------------------------------------- alarme cruzado (WS)


def test_filtro_do_ws_barra_alerta_de_outra_unidade():
    """A ala B nao pode acordar a enfermeira da ala A.

    `useCriticalAlerts` dispara beep e notificacao do navegador para todo alerta
    de alto risco que chega pelo socket. Sem escopo, o alerta da ala vizinha
    acorda quem nao tem nada a ver com ele — e alarme que nao e seu e
    exatamente o que treina a equipe a desligar notificacao.
    """
    from interface.ws_manager_optimized import WebSocketFilter

    da_ala_a = {"severity": "high", "patient_id": "PAC-0001", "unidade_id": 1}
    da_ala_b = {"severity": "high", "patient_id": "PAC-0002", "unidade_id": 2}

    conexao_da_ala_a = WebSocketFilter(unidades={1})

    assert conexao_da_ala_a.matches(da_ala_a)
    assert not conexao_da_ala_a.matches(da_ala_b)


def test_filtro_do_ws_sem_escopo_recebe_tudo():
    """Admin (`unidades=None`) segue recebendo o hospital inteiro."""
    from interface.ws_manager_optimized import WebSocketFilter

    sem_escopo = WebSocketFilter(unidades=None)

    assert sem_escopo.matches({"severity": "high", "unidade_id": 2})
    assert sem_escopo.matches({"severity": "high"})


def test_filtro_do_ws_com_conjunto_vazio_nao_recebe_nada():
    """`set()` e o oposto de `None`, e `if not x:` trata os dois igual."""
    from interface.ws_manager_optimized import WebSocketFilter

    sem_unidade = WebSocketFilter(unidades=set())

    assert not sem_unidade.matches({"severity": "high", "unidade_id": 1})


def test_alerta_sem_unidade_no_payload_nao_vaza():
    """Payload incompleto nao pode ser motivo para entregar dado clinico."""
    from interface.ws_manager_optimized import WebSocketFilter

    escopado = WebSocketFilter(unidades={1})

    assert not escopado.matches({"severity": "high", "patient_id": "PAC-0001"})


def test_payload_de_broadcast_carrega_a_unidade(app_isolado, repo):
    """Se o payload nao trouxer `unidade_id`, o filtro barra por seguranca e o
    alerta nao chega nem na tela da propria ala."""
    from interface.services.alerts_service import montar_payload_alerta_novo

    ana = repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)

    payload = montar_payload_alerta_novo(
        ana["paciente_id"],
        {"inicio": "2026-01-01T08:00:00", "status": "aberto", "perfil": "alto", "tipo": "imobilidade"},
    )

    assert payload["unidade_id"] == UNIDADE_A


# ------------------------------------------------------- administracao


def test_criar_e_vincular_unidade_exigem_admin(client, cabecalho_auth, app_isolado):
    """Quem enxerga a ala nao pode ser quem decide enxerga-la."""
    staff = cabecalho_auth(username="enf.comum", role="staff")

    assert client.post(
        "/api/unidades", json={"nome": "Ala X"}, headers=staff
    ).status_code == 403
    assert client.put(
        "/api/usuarios/enf.comum/unidades", json={"unidades": [1]}, headers=staff
    ).status_code == 403


def test_staff_lista_apenas_as_proprias_unidades(client, cabecalho_auth, app_isolado, unidade_b):
    """LER unidades nao e privilegio: a enfermeira precisa da lista para escolher
    onde admitir. O que muda por papel e o alcance, nao o direito de consultar.
    """
    cab = _usuario_da_unidade(app_isolado, cabecalho_auth, "enf.a", [UNIDADE_A])
    admin = cabecalho_auth(username="chefe", role="admin")

    do_staff = client.get("/api/unidades", headers=cab).json()
    do_admin = client.get("/api/unidades", headers=admin).json()

    assert [u["id"] for u in do_staff] == [UNIDADE_A]
    assert {u["id"] for u in do_admin} == {UNIDADE_A, unidade_b}


def test_admin_cria_unidade_e_vincula_usuario(client, cabecalho_auth, app_isolado, repo):
    admin = cabecalho_auth(username="chefe", role="admin")
    cabecalho_auth(username="enf.nova", role="staff")

    nova = client.post(
        "/api/unidades", json={"nome": "Ala Norte"}, headers=admin
    ).json()
    repo.create(nome="Ana", perfil="alto", cama_id="700-A", unidade_id=nova["id"])

    resposta = client.put(
        "/api/usuarios/enf.nova/unidades",
        json={"unidades": [nova["id"]]},
        headers=admin,
    )
    assert resposta.status_code == 200, resposta.text

    vinculo = client.get("/api/usuarios/enf.nova/unidades", headers=admin).json()
    assert vinculo["unidades"] == [nova["id"]]


def test_remover_vinculo_tem_efeito_imediato(client, cabecalho_auth, app_isolado, repo):
    """Sem limpar o cache, o usuario continuaria vendo por ate 30s a ala da qual
    acabou de ser removido."""
    admin = cabecalho_auth(username="chefe", role="admin")
    cab_enf = _usuario_da_unidade(app_isolado, cabecalho_auth, "enf.saindo", [UNIDADE_A])
    ana = repo.create(nome="Ana", perfil="alto", cama_id="201-A", unidade_id=UNIDADE_A)
    _abrir_alerta(app_isolado.db_path, ana["paciente_id"])

    assert client.get("/api/frontend/alerts", headers=cab_enf).json(), "premissa: via a ala"

    client.put(
        "/api/usuarios/enf.saindo/unidades", json={"unidades": []}, headers=admin
    )

    assert client.get("/api/frontend/alerts", headers=cab_enf).json() == []


def test_admissao_pela_api_respeita_a_unidade_escolhida(
    client, cabecalho_auth, app_isolado, unidade_b
):
    """Sem `unitId` no schema, todo cadastro novo caia na unidade padrao — e a
    tela nao teria como admitir na segunda ala."""
    admin = cabecalho_auth(username="chefe", role="admin")

    resposta = client.post(
        "/api/pacientes",
        json={"name": "Ana", "room": "700", "bed": "A", "riskLevel": "high",
              "unitId": unidade_b},
        headers=admin,
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["unitId"] == unidade_b


def test_admissao_sem_unidade_cai_na_padrao(client, cabecalho_auth, app_isolado):
    """Cliente antigo (e instalacao de uma ala so) continua funcionando."""
    admin = cabecalho_auth(username="chefe", role="admin")

    resposta = client.post(
        "/api/pacientes",
        json={"name": "Bruno", "room": "701", "bed": "A", "riskLevel": "low"},
        headers=admin,
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["unitId"] == UNIDADE_A
