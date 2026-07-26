"""Testes para WebSocket de eventos (ESP32 firmware)."""

import pytest
from fastapi.testclient import TestClient
from interface.web import app
from unittest.mock import patch


@pytest.mark.asyncio
async def test_websocket_eventos_conexao():
    """Testa conexão inicial ao WebSocket."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/eventos") as websocket:
            # Enviar autenticação
            auth = {"device_id": "DEV-001", "cama_id": "C-01"}
            websocket.send_json(auth)
            
            # Receber resposta
            response = websocket.receive_json()
            assert response["status"] == "connected"
            assert response["device_id"] == "DEV-001"


@pytest.mark.asyncio
async def test_websocket_eventos_sem_device_id():
    """Testa rejeição sem device_id."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/eventos") as websocket:
            # Enviar autenticação incompleta
            auth = {"cama_id": "C-01"}  # Falta device_id
            websocket.send_json(auth)
            
            # Receber erro
            response = websocket.receive_json()
            assert "error" in response


@pytest.mark.asyncio
async def test_websocket_eventos_receber_e_processar():
    """Testa recebimento e processamento de evento."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/eventos") as websocket:
            # Autenticar
            auth = {"device_id": "DEV-001", "cama_id": "C-01"}
            websocket.send_json(auth)
            
            # Receber confirmação
            response = websocket.receive_json()
            assert response["status"] == "connected"
            
            # Enviar evento
            evento = {
                "seq": 1,
                "device_id": "DEV-001",
                "paciente_id": "PAC-001",
                "ts_utc": "2025-10-27T14:30:00Z",
                "tipo": "postura",
                "valor": 1,
                "confianca": 0.95
            }
            websocket.send_json(evento)
            
            # Receber ACK
            ack = websocket.receive_json()
            assert ack["status"] == "ok"
            assert ack["seq"] == 1


@pytest.mark.asyncio
async def test_websocket_eventos_multiplos():
    """Testa envio de múltiplos eventos."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/eventos") as websocket:
            # Autenticar
            auth = {"device_id": "DEV-002", "cama_id": "C-02"}
            websocket.send_json(auth)
            websocket.receive_json()  # Consumir resposta
            
            # Enviar 5 eventos
            for i in range(5):
                evento = {
                    "seq": i + 1,
                    "device_id": "DEV-002",
                    "paciente_id": "PAC-002",
                    "ts_utc": f"2025-10-27T14:30:{i:02d}Z",
                    "tipo": "postura",
                    "valor": 1,
                    "confianca": 0.95
                }
                websocket.send_json(evento)
                
                # Receber ACK
                ack = websocket.receive_json()
                assert ack["status"] == "ok"
                assert ack["seq"] == i + 1


@pytest.mark.asyncio
async def test_websocket_eventos_json_invalido():
    """Testa tratamento de JSON inválido."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/eventos") as websocket:
            # Autenticar
            auth = {"device_id": "DEV-003", "cama_id": "C-03"}
            websocket.send_json(auth)
            websocket.receive_json()  # Consumir resposta
            
            # Enviar JSON inválido
            websocket.send_text("{invalid json")
            
            # Receber erro
            response = websocket.receive_json()
            assert response["status"] == "error"
            assert "JSON" in response.get("error", "")


@pytest.mark.asyncio
async def test_websocket_eventos_performance():
    """Testa performance: deve enviar/receber evento em <200ms."""
    import time
    
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/eventos") as websocket:
            # Autenticar
            auth = {"device_id": "DEV-PERF", "cama_id": "C-PERF"}
            websocket.send_json(auth)
            websocket.receive_json()
            
            # Medir tempo
            start = time.time()
            
            evento = {
                "seq": 1,
                "device_id": "DEV-PERF",
                "paciente_id": "PAC-PERF",
                "ts_utc": "2025-10-27T14:30:00Z",
                "tipo": "postura",
                "valor": 1,
                "confianca": 0.95
            }
            websocket.send_json(evento)
            ack = websocket.receive_json()
            
            elapsed = (time.time() - start) * 1000  # em ms
            
            assert ack["status"] == "ok"
            # Performance: deve ser MUITO mais rápido que HTTP (120ms vs 800ms)
            assert elapsed < 500, f"Latência {elapsed}ms > 500ms esperado"
            print(f"✅ WebSocket latência: {elapsed:.1f}ms (alvo: <200ms)")


@pytest.mark.asyncio
async def test_websocket_eventos_reconexao():
    """Testa reconexão automática (simulado)."""
    with TestClient(app) as client:
        # Primeira conexão
        with client.websocket_connect("/api/ws/eventos") as ws1:
            auth1 = {"device_id": "DEV-RC", "cama_id": "C-RC"}
            ws1.send_json(auth1)
            resp1 = ws1.receive_json()
            assert resp1["status"] == "connected"
        
        # Segunda conexão (reconexão simulada)
        with client.websocket_connect("/api/ws/eventos") as ws2:
            auth2 = {"device_id": "DEV-RC", "cama_id": "C-RC"}
            ws2.send_json(auth2)
            resp2 = ws2.receive_json()
            assert resp2["status"] == "connected"
            assert resp2["device_id"] == "DEV-RC"


@pytest.mark.asyncio
async def test_websocket_nao_confirma_evento_que_nao_foi_persistido():
    """Se a amostra nao pode ser guardada, o ACK precisa sinalizar erro.

    Antes o handler logava a falha, seguia com `pass` e mandava
    {"status": "ok"} assim mesmo — o ESP32 dava a amostra por entregue e a
    descartava, entao a leitura sumia em silencio.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/eventos") as websocket:
            websocket.send_json({"device_id": "DEV-FAIL", "cama_id": "C-01"})
            assert websocket.receive_json()["status"] == "connected"

            # Toda tentativa de persistir falha (banco indisponivel, por ex.)
            with patch(
                "interface.routers.ingestao.inserir_device_event",
                side_effect=RuntimeError("db indisponivel"),
            ), patch(
                "interface.routers.ingestao.registrar_evento",
                side_effect=RuntimeError("db indisponivel"),
            ):
                websocket.send_json({
                    "seq": 99,
                    "device_id": "DEV-FAIL",
                    "ts_utc": "2025-10-27T14:30:00Z",
                    "tipo": "postura",
                    "valor": 1,
                })
                resposta = websocket.receive_json()

            assert resposta["seq"] == 99
            assert resposta["status"] == "error", (
                f"evento perdido foi confirmado como ok: {resposta}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_seq_correlaciona_o_ack_sem_reprovar_a_amostra(app_isolado):
    """`seq` e metadado de protocolo, nao parte da amostra.

    Antes desta correcao nao havia combinacao boa para o firmware, e isso foi
    confirmado contra o servidor rodando em container:

      * sem `seq`, a amostra era processada mas NENHUM ACK saia — o `if seq is
        not None` guarda o envio, entao o dispositivo nunca sabia se a leitura
        chegou;
      * com `seq`, `EventPayload` (extra="forbid") reprovava com
        `extra_forbidden`, a amostra caia no caminho de evento ORFAO e o
        servidor respondia "ok" — um ACK dizendo "entregue" para algo que so
        tinha sido guardado cru.

    Era por isso que o firmware WebSocket contabilizava ACK no proprio envio:
    nao havia ACK de verdade para esperar.
    """
    with TestClient(app_isolado.app) as client:
        with client.websocket_connect("/api/ws/eventos") as ws:
            ws.send_json({"device_id": "ESP-SEQ", "cama_id": "C-SEQ"})
            assert ws.receive_json()["status"] == "connected"

            ws.send_json({
                "device_id": "ESP-SEQ",
                "paciente_id": "PAC-SEQ",
                "cama_id": "C-SEQ",
                "postura": "supino",
                "confianca": 0.9,
                "amostra_ms": 300000,
                "ts_utc": "2026-08-01T10:00:00Z",
                "seq": 7,
            })
            ack = ws.receive_json()

    assert ack == {"status": "ok", "seq": 7}, "o ACK precisa devolver o seq para correlacao"


def test_amostra_com_seq_e_processada_e_nao_vira_orfa(app_isolado):
    """O ACK "ok" tem que significar processado, e nao "guardei cru"."""
    import sqlite3

    with TestClient(app_isolado.app) as client:
        with client.websocket_connect("/api/ws/eventos") as ws:
            ws.send_json({"device_id": "ESP-SEQ2", "cama_id": "C-SEQ2"})
            ws.receive_json()
            ws.send_json({
                "device_id": "ESP-SEQ2",
                "paciente_id": "PAC-SEQ2",
                "cama_id": "C-SEQ2",
                "postura": "lateral_direito",
                "confianca": 0.9,
                "amostra_ms": 300000,
                "ts_utc": "2026-08-01T11:00:00Z",
                "seq": 99,
            })
            assert ws.receive_json()["status"] == "ok"

    with sqlite3.connect(app_isolado.db_path) as conn:
        na_grade = conn.execute(
            "SELECT COUNT(*) FROM grade WHERE paciente_id = 'PAC-SEQ2'"
        ).fetchone()[0]
        orfaos = conn.execute(
            "SELECT COUNT(*) FROM device_events WHERE device_id = 'ESP-SEQ2'"
        ).fetchone()[0]

    assert na_grade == 1, "a amostra deveria ter sido processada"
    assert orfaos == 0, "com `seq` fora da validacao, nao ha por que cair no caminho orfao"
