"""Fechado pela equipe e fechado sozinho eram a mesma linha.

Um alerta chega a 'fechado' por dois caminhos:

  1. a enfermagem virou o paciente e clicou na tela (`alterar_status_alerta`);
  2. o motor detectou movimento espontaneo e fechou (`inserir_alertas`, o UPSERT
     em repositories/alertas.py).

Gravavam exatamente a mesma coisa. Consequencia: um paciente que rola sozinho
produzia um "concluido" sem humano nenhum, e `completionRate` — a KPI de capa do
dashboard — media adesao da enfermagem SOMADA a mobilidade do paciente. Para o
TCC isso invalida a variavel de desfecho primaria; para uma ala, invalida a
accountability.

Pior ainda: uma ala cujos sensores param de funcionar gera menos alertas, logo
denominador menor, logo taxa melhor.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from interface.db_core import connect
from interface.repositories.alertas import (
    ORIGEM_EQUIPE,
    ORIGEM_SENSOR,
    alterar_status_alerta,
    inserir_alertas,
)
from interface.tempo import agora_utc_naive

PACIENTE = "PAC-0001"


@pytest.fixture
def db(app_isolado):
    caminho = app_isolado.db_path
    with connect(caminho) as conn:
        conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (PACIENTE,))
        agora = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute(
            "INSERT INTO paciente_fichas(paciente_id,nome,perfil,cama_id,created_at,updated_at)"
            " VALUES (?,'Ana','alto','201-A',?,?)",
            (PACIENTE, agora, agora),
        )
    return caminho


def _abrir(db, minutos_atras: int = 90) -> str:
    inicio = (agora_utc_naive() - timedelta(minutes=minutos_atras)).strftime("%Y-%m-%dT%H:%M:%S")
    inserir_alertas(db, [{
        "paciente_id": PACIENTE, "inicio": inicio, "tipo": "imobilidade",
        "perfil": "alto", "janela_min": 60, "status": "aberto",
    }])
    return inicio


def _linha(db, inicio: str) -> dict:
    with connect(db) as conn:
        return dict(conn.execute(
            "SELECT status, fechado_por, origem_fechamento FROM alertas"
            " WHERE paciente_id = ? AND inicio = ?",
            (PACIENTE, inicio),
        ).fetchone())


def test_fechamento_pelo_motor_fica_marcado_como_sensor(db):
    """O motor emite o mesmo alerta duas vezes: aberto e depois fechado."""
    inicio = _abrir(db)
    fim = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")

    inserir_alertas(db, [{
        "paciente_id": PACIENTE, "inicio": inicio, "fim": fim, "tipo": "imobilidade",
        "perfil": "alto", "janela_min": 60, "status": "fechado", "duracao_min": 30.0,
    }])

    linha = _linha(db, inicio)
    assert linha["status"] == "fechado"
    assert linha["origem_fechamento"] == ORIGEM_SENSOR
    assert linha["fechado_por"] is None, "movimento espontaneo nao tem autor"


def test_fechamento_pela_equipe_registra_quem(db):
    inicio = _abrir(db)

    alterar_status_alerta(
        db, PACIENTE, inicio, "fechado", definir_fim=True,
        fechado_por="enfermeira.ana", origem_fechamento=ORIGEM_EQUIPE,
    )

    linha = _linha(db, inicio)
    assert linha["origem_fechamento"] == ORIGEM_EQUIPE
    assert linha["fechado_por"] == "enfermeira.ana"


def test_origem_invalida_e_recusada(db):
    inicio = _abrir(db)
    with pytest.raises(ValueError):
        alterar_status_alerta(
            db, PACIENTE, inicio, "fechado", definir_fim=True,
            origem_fechamento="chute",
        )


def test_autoria_nao_e_reescrita_por_um_segundo_clique(db):
    """`fim` ja tinha essa garantia; a autoria precisa herda-la.

    Sem isso, dois cliques em telas diferentes — rotina numa ala — trocariam o
    autor registrado pelo do segundo clique.
    """
    inicio = _abrir(db)
    alterar_status_alerta(
        db, PACIENTE, inicio, "fechado", definir_fim=True,
        fechado_por="primeira", origem_fechamento=ORIGEM_EQUIPE,
    )
    alterar_status_alerta(
        db, PACIENTE, inicio, "fechado", definir_fim=True,
        fechado_por="segunda", origem_fechamento=ORIGEM_EQUIPE,
    )

    assert _linha(db, inicio)["fechado_por"] == "primeira"


def test_stats_separa_adesao_da_equipe_de_movimento_espontaneo(db, app_isolado, cabecalho_auth):
    """A pergunta da coordenacao — "a equipe esta virando os pacientes?" — nao
    era respondivel: os dois casos caiam no mesmo contador."""
    # Um alerta fechado pelo sensor.
    inicio_sensor = _abrir(db, minutos_atras=200)
    inserir_alertas(db, [{
        "paciente_id": PACIENTE, "inicio": inicio_sensor,
        "fim": agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S"),
        "tipo": "imobilidade", "perfil": "alto", "janela_min": 60,
        "status": "fechado", "duracao_min": 10.0,
    }])

    # Um alerta fechado pela equipe.
    inicio_equipe = _abrir(db, minutos_atras=100)
    alterar_status_alerta(
        db, PACIENTE, inicio_equipe, "fechado", definir_fim=True,
        fechado_por="enfermeira.ana", origem_fechamento=ORIGEM_EQUIPE,
    )

    client = TestClient(app_isolado.app)
    stats = client.get("/api/stats", headers=cabecalho_auth()).json()

    assert stats["completedToday"] == 2, "os dois continuam contando como concluidos"
    assert stats["completedByTeam"] == 1
    assert stats["completedBySensor"] == 1
    assert stats["teamCompletionRate"] < stats["completionRate"], (
        "a taxa de adesao da equipe nao pode ser inflada pelo movimento espontaneo"
    )


def test_endpoint_de_completar_grava_autor_e_avisa_o_motor(db, app_isolado, cabecalho_auth):
    """Pela porta que a enfermeira realmente usa, nao pelo repositorio.

    Cobre 0.2 e 0.3 no mesmo caminho: o clique precisa gravar a autoria E
    limpar o alerta fantasma do motor. Um teste que so chame o repositorio nao
    prova que o router esta ligado nos dois.
    """
    from interface.services.ingestao_service import PROCESSADOR
    from nucleo.decisor import EstadoDecisor

    inicio = _abrir(db, minutos_atras=90)

    # Motor com alerta aberto para este paciente, como estaria em producao.
    estado = EstadoDecisor.criar("alto", PACIENTE)
    estado.alerta_atual = {"paciente_id": PACIENTE, "inicio": inicio}
    estado.alerta_inicio = agora_utc_naive()
    estado.baseline_postura = "supino"
    PROCESSADOR._estado_cache[PACIENTE] = estado

    client = TestClient(app_isolado.app)
    resposta = client.post(
        f"/api/frontend/alerts/{PACIENTE}__{inicio}/complete",
        headers=cabecalho_auth(username="enfermeira.ana"),
    )
    assert resposta.status_code == 200, resposta.text

    linha = _linha(db, inicio)
    assert linha["origem_fechamento"] == ORIGEM_EQUIPE
    assert linha["fechado_por"] == "enfermeira.ana"

    assert PROCESSADOR._estado_cache[PACIENTE].alerta_atual is None, (
        "o motor seguiu com o alerta fantasma e o paciente ficaria sem alerta novo"
    )


def test_lote_tambem_grava_autor_e_avisa_o_motor(db, app_isolado, cabecalho_auth):
    """O botao "selecionar tudo" da tela e por onde passa a maior parte dos
    fechamentos. Esquecer o lote deixaria os dois defeitos vivos justamente no
    caminho mais usado."""
    from interface.services.ingestao_service import PROCESSADOR
    from nucleo.decisor import EstadoDecisor

    inicio = _abrir(db, minutos_atras=90)

    estado = EstadoDecisor.criar("alto", PACIENTE)
    estado.alerta_atual = {"paciente_id": PACIENTE, "inicio": inicio}
    estado.alerta_inicio = agora_utc_naive()
    estado.baseline_postura = "supino"
    PROCESSADOR._estado_cache[PACIENTE] = estado

    client = TestClient(app_isolado.app)
    resposta = client.post(
        "/api/frontend/alerts/batch/complete",
        json={"alert_ids": [f"{PACIENTE}__{inicio}"]},
        headers=cabecalho_auth(username="enfermeira.ana"),
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["processed"] == 1

    linha = _linha(db, inicio)
    assert linha["origem_fechamento"] == ORIGEM_EQUIPE
    assert linha["fechado_por"] == "enfermeira.ana"
    assert PROCESSADOR._estado_cache[PACIENTE].alerta_atual is None


def test_linhas_antigas_ficam_como_origem_desconhecida(db, app_isolado, cabecalho_auth):
    """Alertas anteriores a migration ficam NULL de proposito.

    Nao da para saber retroativamente qual caminho fechou cada um, e chutar
    'equipe' inventaria adesao que talvez nunca tenha existido. O numero fica
    explicitamente parcial em vez de bonito e falso.
    """
    inicio = _abrir(db, minutos_atras=100)
    with connect(db) as conn:
        conn.execute(
            "UPDATE alertas SET status='fechado', fim=?, origem_fechamento=NULL"
            " WHERE paciente_id=? AND inicio=?",
            (agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S"), PACIENTE, inicio),
        )

    client = TestClient(app_isolado.app)
    stats = client.get("/api/stats", headers=cabecalho_auth()).json()

    assert stats["completedToday"] == 1
    assert stats["completedByTeam"] == 0
    assert stats["completedUnknownOrigin"] == 1
