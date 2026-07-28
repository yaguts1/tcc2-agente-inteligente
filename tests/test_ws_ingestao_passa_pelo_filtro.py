"""As duas portas de ingestao tratavam a amostra de forma diferente.

`POST /api/eventos` passa por `quality/filtro.py` (dedup por device+postura+ts e
buffer de reordenacao por jitter) antes de virar dado clinico. O WebSocket
`/api/ws/eventos` chamava `registrar_evento` direto.

Isso importa porque o WebSocket e o transporte que o firmware trata como
primario (`firmware/esp32_replay/transporte_ws.h`) e o que mais retransmite: o
ACK e assincrono, com `TIMEOUT_ACK_MS`, entao um ACK atrasado faz o device
mandar de novo. Sem dedup, a retransmissao virava uma segunda amostra na grade
do paciente.

O limiar de confianca seguia valendo (aplicado adiante, em
`processamento_incremental`), entao o buraco era dedup e ordenacao — suficiente
para as duas portas discordarem sobre o que entra no historico do paciente.
"""

import pytest
from fastapi.testclient import TestClient

from interface.db_core import connect

TS = "2026-03-10T10:00:00"


@pytest.fixture
def client(app_isolado):
    from quality.filtro import reset_filtro

    # O estado do filtro (dedup e buffer de jitter) e de MODULO: sem limpar, o
    # que um teste anterior enviou decide o resultado deste.
    reset_filtro()

    with TestClient(app_isolado.app) as c:
        yield c


def _evento(seq: int, ts: str = TS) -> dict:
    return {
        "seq": seq,
        "device_id": "DEV-001",
        "paciente_id": "PAC-0001",
        "cama_id": "C-01",
        "postura": "supino",
        "confianca": 0.95,
        "amostra_ms": 60000,
        "ts_utc": ts,
    }


def _amostras_na_grade(db_path: str) -> int:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM grade WHERE paciente_id = 'PAC-0001'"
        ).fetchone()[0]


def _descartes() -> float:
    from servicos.metricas import EVENTOS_DESCARTADOS

    return EVENTOS_DESCARTADOS._value.get()


def test_retransmissao_e_reconhecida_como_duplicata(client, app_isolado):
    """O device reenvia quando o ACK demora; o filtro precisa VER isso.

    A contagem de linhas na grade nao serve para provar nada aqui: a PK
    `(paciente_id, ts)` com `INSERT OR IGNORE` engole a duplicata de qualquer
    jeito, entao um teste de contagem passa igual com e sem filtro — foi
    exatamente assim que este buraco sobreviveu.

    O que muda e o sistema SABER: pelo filtro, a retransmissao e contabilizada
    como descarte (`eventos_descartados_total`, a metrica que diz quanto do
    trafego do device e ruido); sem filtro, ela sumia dentro do `OR IGNORE` sem
    aparecer em lugar nenhum.
    """
    antes = _descartes()

    with client.websocket_connect("/api/ws/eventos") as ws:
        ws.send_json({"device_id": "DEV-001", "cama_id": "C-01"})
        assert ws.receive_json()["status"] == "connected"

        for seq in (1, 2):  # mesma amostra, dois envios
            ws.send_json(_evento(seq))
            assert ws.receive_json() == {"status": "ok", "seq": seq}

    assert _descartes() > antes, (
        "a retransmissao do device passou sem o filtro sequer notar"
    )
    assert _amostras_na_grade(app_isolado.db_path) == 1


def test_amostra_valida_continua_chegando_na_grade(client, app_isolado):
    """Ancora: se o filtro engolisse tudo, o teste acima passaria por engano."""
    with client.websocket_connect("/api/ws/eventos") as ws:
        ws.send_json({"device_id": "DEV-001", "cama_id": "C-01"})
        ws.receive_json()

        ws.send_json(_evento(1))
        assert ws.receive_json() == {"status": "ok", "seq": 1}

    assert _amostras_na_grade(app_isolado.db_path) == 1
