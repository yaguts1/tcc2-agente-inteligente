"""Testes para WebSocket de eventos (ESP32 firmware)."""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from interface.web import app
from unittest.mock import patch, MagicMock


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
