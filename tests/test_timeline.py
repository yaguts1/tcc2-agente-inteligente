
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pathlib import Path
from datetime import datetime

from interface.dao import criar_paciente, inserir_timeline_event


@pytest_asyncio.fixture()
async def api_client(app_isolado, cabecalho_auth):
    """A cadeia de reload de 12 modulos que vivia aqui (copiada tambem em
    test_api.py e test_api_ingestao.py) virou a fixture `app_isolado` em
    tests/conftest.py.

    /api/timeline expoe dados clinicos e exige sessao, entao o client carrega
    um JWT REAL — nunca um token forjado.
    """
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth()
    ) as client:
        yield {"client": client, "db_path": Path(app_isolado.db_path)}


@pytest.mark.asyncio
async def test_timeline_exige_autenticacao(app_isolado):
    """Sem credencial, /api/timeline responde 401."""
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as anon:
        resp = await anon.get("/api/timeline")
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_get_timeline_empty(api_client):
    client = api_client["client"]
    resp = await client.get("/api/timeline")
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.asyncio
async def test_get_timeline_with_events(api_client):
    client = api_client["client"]
    db_path = api_client["db_path"]
    
    # Create patient
    ficha = criar_paciente(str(db_path), "João Silva", "alto")
    pid = ficha["paciente_id"]
    
    # Insert events
    ts_now = datetime.now().isoformat()
    ts_ms = int(datetime.now().timestamp() * 1000)
    
    inserir_timeline_event(str(db_path), pid, ts_now, ts_ms, "alert_open", "Alerta aberto")
    inserir_timeline_event(str(db_path), pid, ts_now, ts_ms + 1000, "alert_close", "Alerta fechado")
    
    # Fetch timeline
    resp = await client.get("/api/timeline")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2
    assert events[0]["paciente_id"] == pid
    assert events[0]["paciente_name"] == "João Silva"
    # Now ordered by DESC (newest first)
    assert events[0]["tipo"] == "alert_close"
    assert events[1]["tipo"] == "alert_open"

@pytest.mark.asyncio
async def test_get_timeline_filter_tipo(api_client):
    client = api_client["client"]
    db_path = api_client["db_path"]
    
    ficha = criar_paciente(str(db_path), "Maria", "medio")
    pid = ficha["paciente_id"]
    
    ts_now = datetime.now().isoformat()
    ts_ms = int(datetime.now().timestamp() * 1000)
    
    inserir_timeline_event(str(db_path), pid, ts_now, ts_ms, "type_a")
    inserir_timeline_event(str(db_path), pid, ts_now, ts_ms, "type_b")
    
    resp = await client.get("/api/timeline?tipo=type_a")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    assert events[0]["tipo"] == "type_a"

@pytest.mark.asyncio
async def test_get_timeline_filter_paciente(api_client):
    client = api_client["client"]
    db_path = api_client["db_path"]
    
    p1 = criar_paciente(str(db_path), "P1", "baixo")
    p2 = criar_paciente(str(db_path), "P2", "baixo")
    
    ts_now = datetime.now().isoformat()
    ts_ms = int(datetime.now().timestamp() * 1000)
    
    inserir_timeline_event(str(db_path), p1["paciente_id"], ts_now, ts_ms, "ev1")
    inserir_timeline_event(str(db_path), p2["paciente_id"], ts_now, ts_ms, "ev2")
    
    resp = await client.get(f"/api/timeline?paciente_id={p1['paciente_id']}")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    assert events[0]["paciente_id"] == p1["paciente_id"]
