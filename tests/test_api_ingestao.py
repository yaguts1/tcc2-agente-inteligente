from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest_asyncio.fixture()
async def api_client(app_isolado):
    """Usa a fixture compartilhada `app_isolado` (tests/conftest.py).

    A ingestao nao usa JWT de usuario: autentica por token de dispositivo, que
    o conftest deixa desconfigurado — nesse modo a verificacao fica desligada,
    entao nao ha header a enviar aqui.
    """
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "client": client,
            "db_path": Path(app_isolado.db_path),
            "api": importlib.import_module("interface.api"),
        }


@pytest.mark.asyncio
async def test_evento_duplicado_descartado(api_client):
    client = api_client["client"]
    payload = {
        "device_id": "ESP1",
        "paciente_id": "PAC-001",
        "cama_id": "C01",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 300000,
        "ts_utc": "2025-01-01T00:00:00Z",
    }

    resp1 = await client.post("/api/eventos", json=payload)
    assert resp1.status_code == 200
    resp2 = await client.post("/api/eventos", json=payload)
    assert resp2.status_code == 200
    corpo2 = resp2.json()
    assert corpo2["code"] == "accepted"
    assert corpo2["ids"]["processados"] == 0


@pytest.mark.asyncio
async def test_evento_fora_de_ordem_sem_alerta(api_client):
    client = api_client["client"]
    base = {
        "device_id": "ESP1",
        "paciente_id": "PAC-002",
        "cama_id": "C02",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 300000,
    }
    resp1 = await client.post("/api/eventos", json={**base, "ts_utc": "2025-01-01T00:10:00Z"})
    assert resp1.status_code == 200
    resp2 = await client.post("/api/eventos", json={**base, "ts_utc": "2025-01-01T00:05:00Z"})
    assert resp2.status_code == 200
    corpo2 = resp2.json()
    assert corpo2["ids"]["alertas"] == 0


@pytest.mark.asyncio
async def test_evento_ruido_descartado(api_client):
    client = api_client["client"]
    payload = {
        "device_id": "ESP1",
        "paciente_id": "PAC-003",
        "cama_id": "C03",
        "postura": "supino",
        "confianca": 0.2,
        "amostra_ms": 300000,
        "ts_utc": "2025-01-01T00:00:00Z",
    }
    resp = await client.post("/api/eventos", json=payload)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["code"] == "accepted"
    assert corpo["ids"]["processados"] == 0


@pytest.mark.asyncio
async def test_grade_jsonl_processa_somente_validos(api_client):
    client = api_client["client"]
    arquivo = FIXTURES_DIR / "eventos_validos.jsonl"
    files = {"arquivo": (arquivo.name, arquivo.read_bytes(), "application/jsonl")}

    resp = await client.post("/api/grade", files=files)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["code"] == "success"
    assert corpo["ids"]["processados"] == 3

    with sqlite3.connect(api_client["db_path"]) as conn:
        total = conn.execute("SELECT COUNT(*) FROM grade").fetchone()[0]
    assert total == 3


@pytest.mark.asyncio
async def test_grade_jsonl_ruido(api_client):
    client = api_client["client"]
    arquivo = FIXTURES_DIR / "ruidos.jsonl"
    files = {"arquivo": (arquivo.name, arquivo.read_bytes(), "application/jsonl")}

    resp = await client.post("/api/grade", files=files)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["ids"]["processados"] == 0
