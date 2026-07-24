
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from importlib import reload
from pathlib import Path
import sqlite3
from datetime import datetime

from interface.dao import criar_esquema, criar_paciente, inserir_timeline_event

@pytest_asyncio.fixture()
async def api_client(tmp_path, monkeypatch):
    tmp_db = tmp_path / "dados.db"
    monkeypatch.setenv("UPP_DB_PATH", str(tmp_db))
    criar_esquema(str(tmp_db))

    # Importacao tardia para respeitar as variaveis de ambiente definidas acima.
    import interface.api_shared as api_shared
    import interface.routers.auth as auth
    import interface.routers.pacientes as pacientes
    import interface.routers.devices as devices
    import interface.routers.alerts as alerts
    import interface.routers.dashboard as dashboard
    import interface.services.ingestao_service as ingestao_service
    import interface.routers.ingestao as ingestao
    import interface.routers.backup as backup
    import interface.routers.admin as admin
    import interface.web as web_module
    from interface import api as api_module

    reload(api_shared)
    reload(auth)
    reload(pacientes)
    reload(devices)
    reload(alerts)
    reload(dashboard)
    reload(ingestao_service)
    reload(ingestao)
    reload(backup)
    reload(admin)
    reload(api_module)
    reload(web_module)

    api_module.reset_processador()
    api_module.reset_rate_limiter()

    transport = ASGITransport(app=web_module.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {"client": client, "db_path": tmp_db}

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
