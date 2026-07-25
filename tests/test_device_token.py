"""Autenticacao dos dispositivos (ESP32) na ingestao.

O firmware so enviava `X-Device-Id`, escolhido por ele mesmo: identifica, mas
nao autentica — e ainda permitia furar o rate limit trocando o header. Quem
alcancasse a rede podia injetar leituras de sensor em nome de um paciente.

UPP_DEVICE_TOKEN e o segredo compartilhado que fecha isso. Quando NAO esta
definido a verificacao fica desligada de proposito (para nao derrubar bancadas
ja montadas) e o app avisa no startup.
"""

import pytest
from fastapi.testclient import TestClient

from interface.web import app

EVENTO = {
    "device_id": "ESP32-A",
    "ts_utc": "2026-07-25T10:00:00Z",
    "postura": "supino",
    "amostra_ms": 1000,
}
TOKEN = "token-de-teste-123"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def com_token(monkeypatch):
    monkeypatch.setenv("UPP_DEVICE_TOKEN", TOKEN)


@pytest.fixture
def sem_token(monkeypatch):
    monkeypatch.delenv("UPP_DEVICE_TOKEN", raising=False)


def test_ingestao_rejeita_sem_token(client, com_token):
    resp = client.post("/api/eventos", json=EVENTO, headers={"X-Device-Id": "ESP32-A"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "device_nao_autenticado"


def test_ingestao_rejeita_token_errado(client, com_token):
    resp = client.post(
        "/api/eventos",
        json=EVENTO,
        headers={"X-Device-Id": "ESP32-A", "X-Device-Token": "errado"},
    )
    assert resp.status_code == 401


def test_ingestao_aceita_token_correto(client, com_token):
    resp = client.post(
        "/api/eventos",
        json=EVENTO,
        headers={"X-Device-Id": "ESP32-A", "X-Device-Token": TOKEN},
    )
    # Pode falhar na validacao do payload (422), mas nao pode ser 401.
    assert resp.status_code != 401


def test_endpoint_do_firmware_exige_token(client, com_token):
    """GET /api/pacientes/cama/{id} e consumido pelo ESP32: vale o token de
    dispositivo, nao o JWT de usuario."""
    assert client.get("/api/pacientes/cama/101").status_code == 401
    assert client.get(
        "/api/pacientes/cama/101", headers={"X-Device-Token": TOKEN}
    ).status_code != 401


def test_websocket_rejeita_sem_token(client, com_token):
    with client.websocket_connect("/api/ws/eventos") as ws:
        ws.send_json({"device_id": "ESP32-A", "cama_id": "101"})
        resp = ws.receive_json()
    assert resp["error"] == "invalid_device_token"


def test_websocket_aceita_token_no_corpo(client, com_token):
    """A lib de WebSocket do ESP32 nao permite header no handshake, entao o
    token tambem e aceito no payload de auth."""
    with client.websocket_connect("/api/ws/eventos") as ws:
        ws.send_json({"device_id": "ESP32-A", "cama_id": "101", "token": TOKEN})
        resp = ws.receive_json()
    assert resp["status"] == "connected"


def test_sem_token_configurado_ingestao_segue_aberta(client, sem_token):
    """Valvula de seguranca: sem UPP_DEVICE_TOKEN nada e exigido, para nao
    quebrar bancadas existentes. O aviso sai no startup."""
    resp = client.post("/api/eventos", json=EVENTO, headers={"X-Device-Id": "ESP32-A"})
    assert resp.status_code != 401
