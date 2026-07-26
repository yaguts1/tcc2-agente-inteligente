"""O que a equipe ve e o que ela registra ao agir.

Tres defeitos que atingiam justamente o dado que este sistema existe para
produzir: quando o paciente precisa ser virado, e quando ele foi virado.
"""

import asyncio
import sqlite3
import time
from datetime import timedelta

import pytest

from interface.dao import inserir_alertas
from interface.repositories.alertas import (
    TransicaoInvalida,
    alterar_status_alerta,
    selecionar_alertas_janela,
)
from interface.tempo import agora_utc_naive

INICIO = "2026-07-25T10:00:00"


def _alerta(paciente_id="P", inicio=INICIO, status="aberto", fim=None):
    return {
        "paciente_id": paciente_id,
        "inicio": inicio,
        "fim": fim,
        "tipo": "imobilidade",
        "perfil": "alto",
        "janela_min": 60,
        "status": status,
        "duracao_min": None,
    }


@pytest.fixture
def db(app_isolado):
    caminho = app_isolado.db_path
    inserir_alertas(caminho, [_alerta()])
    return caminho


def _linha(db, paciente_id="P", inicio=INICIO):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT status, fim, duracao_min FROM alertas WHERE paciente_id=? AND inicio=?",
            (paciente_id, inicio),
        ).fetchone()


# --------------------------------------------------------------------------
# 1. Alerta nao resolvido nunca sai da lista
# --------------------------------------------------------------------------


def test_alerta_aberto_antigo_continua_visivel(app_isolado):
    """O paciente MAIS atrasado era o que sumia.

    O filtro olhava so `inicio`, sem considerar o status: um alerta aberto ha
    25 horas e nunca atendido caia fora da janela de 24h e desaparecia da tela
    e do /api/stats — sem contador nem aviso de que havia algo fora da janela.
    """
    agora = agora_utc_naive()
    for horas, nome in ((2, "PAC-2h"), (23, "PAC-23h"), (25, "PAC-25h"), (72, "PAC-72h")):
        inserir_alertas(
            app_isolado.db_path,
            [_alerta(
                paciente_id=nome,
                inicio=(agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S"),
            )],
        )

    visiveis = {a["paciente_id"] for a in selecionar_alertas_janela(app_isolado.db_path, horas=24)}

    assert visiveis == {"PAC-2h", "PAC-23h", "PAC-25h", "PAC-72h"}, (
        f"alertas abertos sumiram da lista: {{'PAC-25h','PAC-72h'}} - {visiveis}"
    )


def test_alerta_reconhecido_antigo_tambem_continua_visivel(app_isolado):
    """Reconhecido nao e resolvido: o paciente ainda precisa ser virado."""
    inicio = (agora_utc_naive() - timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%S")
    inserir_alertas(app_isolado.db_path, [_alerta(paciente_id="PAC-ACK", inicio=inicio)])
    alterar_status_alerta(app_isolado.db_path, "PAC-ACK", inicio, "reconhecido")

    visiveis = {a["paciente_id"] for a in selecionar_alertas_janela(app_isolado.db_path, horas=24)}

    assert "PAC-ACK" in visiveis


def test_alerta_fechado_antigo_sai_da_janela(app_isolado):
    """A janela continua valendo para o HISTORICO — senao a tela vira arquivo."""
    inicio = (agora_utc_naive() - timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%S")
    inserir_alertas(
        app_isolado.db_path,
        [_alerta(paciente_id="PAC-OLD", inicio=inicio, status="fechado", fim=inicio)],
    )

    visiveis = {a["paciente_id"] for a in selecionar_alertas_janela(app_isolado.db_path, horas=24)}

    assert "PAC-OLD" not in visiveis


# --------------------------------------------------------------------------
# 2. O status so anda para a frente
# --------------------------------------------------------------------------


def test_concluir_duas_vezes_preserva_o_instante_do_reposicionamento(db):
    """`fim` e o registro de quando o paciente foi virado. Nao se reescreve.

    Antes, o segundo clique sobrescrevia `fim` e `duracao_min` — o horario real
    do reposicionamento era trocado pelo do clique repetido.
    """
    alterar_status_alerta(db, "P", INICIO, "fechado", definir_fim=True)
    _, fim_original, duracao_original = _linha(db)

    time.sleep(1.1)
    alterar_status_alerta(db, "P", INICIO, "fechado", definir_fim=True)

    status, fim, duracao = _linha(db)
    assert status == "fechado"
    assert fim == fim_original, "o horario do reposicionamento foi sobrescrito"
    assert duracao == duracao_original


def test_nao_volta_de_concluido_para_reconhecido(db):
    """Um paciente ja virado nao pode voltar a aparecer como pendente."""
    alterar_status_alerta(db, "P", INICIO, "fechado", definir_fim=True)

    with pytest.raises(TransicaoInvalida):
        alterar_status_alerta(db, "P", INICIO, "reconhecido")

    assert _linha(db)[0] == "fechado"


def test_nao_volta_para_aberto(db):
    alterar_status_alerta(db, "P", INICIO, "reconhecido")

    with pytest.raises(TransicaoInvalida):
        alterar_status_alerta(db, "P", INICIO, "aberto")

    assert _linha(db)[0] == "reconhecido"


def test_reconhecer_e_idempotente(db):
    """Clique duplo, ou retry de requisicao, nao pode alterar nada."""
    alterar_status_alerta(db, "P", INICIO, "reconhecido")
    antes = _linha(db)

    alterar_status_alerta(db, "P", INICIO, "reconhecido")

    assert _linha(db) == antes


def test_avanco_normal_funciona(db):
    """aberto -> reconhecido -> fechado, que e o fluxo da equipe."""
    alterar_status_alerta(db, "P", INICIO, "reconhecido")
    assert _linha(db)[0] == "reconhecido"

    alterar_status_alerta(db, "P", INICIO, "fechado", definir_fim=True)
    status, fim, duracao = _linha(db)
    assert status == "fechado"
    assert fim is not None and duracao is not None


def test_status_desconhecido_e_recusado(db):
    with pytest.raises(ValueError):
        alterar_status_alerta(db, "P", INICIO, "concluido_talvez")


# --------------------------------------------------------------------------
# 3. A acao nao pode custar 5 segundos
# --------------------------------------------------------------------------


def test_acao_nao_bloqueia_no_lock_do_proprio_banco(db):
    """`alterar_status_alerta` abria uma transacao de escrita e, DENTRO dela,
    chamava `inserir_timeline_event`, que abre outra conexao ao mesmo arquivo.

    A segunda conexao esperava o `busy_timeout` inteiro (5 s) e falhava sempre
    — deterministicamente. Cada clique custava 5 s a mais, em lote 5 s x N, e o
    log recebia um stack trace de "database is locked" por acao, ruido que
    mascara falha de verdade. O evento de timeline ja e gravado pelo servico,
    fora da transacao, entao a tentativa no DAO so custava tempo.
    """
    inicio = time.perf_counter()
    alterar_status_alerta(db, "P", INICIO, "reconhecido")
    decorrido = time.perf_counter() - inicio

    assert decorrido < 1.0, f"a operacao levou {decorrido:.1f}s (o busy_timeout e 5s)"


def test_api_recusa_retrocesso_com_409(app_isolado):
    """A segunda pessoa precisa saber que nao foi ela quem registrou."""
    from fastapi.testclient import TestClient

    import interface.services.alerts_service as svc

    svc.DB_PATH = app_isolado.db_path
    inserir_alertas(app_isolado.db_path, [_alerta(paciente_id="PAC-409")])
    alert_id = f"PAC-409__{INICIO}"

    with TestClient(app_isolado.app) as client:
        client.post("/api/auth/register", json={"username": "enf", "password": "senha-de-teste"})
        client.post("/api/auth/login", json={"username": "enf", "password": "senha-de-teste"})

        assert client.post(f"/api/frontend/alerts/{alert_id}/complete").status_code == 200
        resposta = client.post(f"/api/frontend/alerts/{alert_id}/acknowledge")

    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["detail"]["code"] == "transicao_invalida"


def test_concluir_duas_vezes_pela_api_responde_ok(app_isolado):
    """Repetir a MESMA acao e idempotente — nao e conflito, e o mesmo desfecho."""
    from fastapi.testclient import TestClient

    import interface.services.alerts_service as svc

    svc.DB_PATH = app_isolado.db_path
    inserir_alertas(app_isolado.db_path, [_alerta(paciente_id="PAC-IDEM")])
    alert_id = f"PAC-IDEM__{INICIO}"

    with TestClient(app_isolado.app) as client:
        client.post("/api/auth/register", json={"username": "enf2", "password": "senha-de-teste"})
        client.post("/api/auth/login", json={"username": "enf2", "password": "senha-de-teste"})

        assert client.post(f"/api/frontend/alerts/{alert_id}/complete").status_code == 200
        assert client.post(f"/api/frontend/alerts/{alert_id}/complete").status_code == 200

    assert _linha(app_isolado.db_path, "PAC-IDEM")[0] == "fechado"


def test_stats_conta_o_paciente_mais_atrasado(app_isolado):
    """O /api/stats usava a mesma consulta: um paciente 30h sem virar nao
    entrava em `activeAlerts` e nao aparecia em lugar nenhum do sistema."""
    import interface.services.alerts_service as svc

    svc.DB_PATH = app_isolado.db_path
    inicio = (agora_utc_naive() - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%S")
    inserir_alertas(app_isolado.db_path, [_alerta(paciente_id="PAC-30h", inicio=inicio)])

    asyncio.run(svc.api_cache.clear())
    alertas = asyncio.run(svc.listar_alertas_frontend(horas=24))

    assert any(a["id"].startswith("PAC-30h") for a in alertas), (
        "o paciente com 30h de atraso nao aparece na listagem"
    )


def test_timeline_grava_ts_no_formato_do_banco(app_isolado):
    """Um unico formato de `ts` na coluna.

    Os eventos de reconhecer/concluir gravavam
    `2026-07-25T03:42:24.229283+00:00` enquanto todos os demais usam
    `2026-07-25T03:42:24`. Nao quebrava nada (a ordenacao usa `ts_ms` e o
    endpoint normaliza), mas duas convencoes na mesma coluna e uma armadilha
    para o proximo que ler `ts` direto.
    """
    import re

    from fastapi.testclient import TestClient

    import interface.services.alerts_service as svc

    svc.DB_PATH = app_isolado.db_path
    inserir_alertas(app_isolado.db_path, [_alerta(paciente_id="PAC-TS")])

    with TestClient(app_isolado.app) as client:
        client.post("/api/auth/register", json={"username": "enf3", "password": "senha-de-teste"})
        client.post("/api/auth/login", json={"username": "enf3", "password": "senha-de-teste"})
        client.post(f"/api/frontend/alerts/PAC-TS__{INICIO}/acknowledge")

    with sqlite3.connect(app_isolado.db_path) as conn:
        timestamps = [
            linha[0]
            for linha in conn.execute("SELECT ts FROM timeline_events WHERE paciente_id='PAC-TS'")
        ]

    assert timestamps
    for ts in timestamps:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts), (
            f"ts fora do formato UTC naive do banco: {ts!r}"
        )
