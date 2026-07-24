"""Tests to ensure datetime fields in API contracts are ISO strings (naive) and
that EventPayload normalizes timezone-aware timestamps to naive UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import interface.api as api_mod
import interface.api_shared as api_shared
import interface.routers.alerts as alerts_router
from importlib import reload
from interface.dao import criar_esquema, inserir_alertas
from interface.schemas import EventPayload


@pytest.mark.asyncio
async def test_frontend_alerts_datetimes_are_iso_naive(tmp_path, monkeypatch):
    db_path = tmp_path / "dados.db"
    criar_esquema(db_path)
    
    monkeypatch.setenv("UPP_DB_PATH", str(db_path))
    reload(api_shared)
    reload(alerts_router)
    reload(api_mod)

    now = datetime.now().replace(microsecond=0)
    alert = {
        "paciente_id": "DT-1",
        "inicio": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "fim": None,
        "tipo": "imobilidade",
        "perfil": "medio",
        "janela_min": 60,
        "status": "aberto",
        "duracao_min": None,
    }
    assert inserir_alertas(str(db_path), [alert]) == 1

    results = await api_mod.frontend_alerts(horas=24)
    assert results, "No alerts returned"
    for r in results:
        lr = r.get("lastRepositioning")
        nr = r.get("nextRepositioning")
        # should be strings parseable by datetime.fromisoformat and produce naive datetimes
        if lr is not None:
            parsed = datetime.fromisoformat(lr)
            assert parsed.tzinfo is None, f"lastRepositioning should be naive ISO string, got tzinfo: {lr}"
        if nr is not None:
            parsed2 = datetime.fromisoformat(nr)
            assert parsed2.tzinfo is None, f"nextRepositioning should be naive ISO string, got tzinfo: {nr}"


def test_eventpayload_normalizes_tz_to_naive_utc():
    # supply a tz-aware timestamp (UTC) and ensure model normalizes to naive UTC
    aware = datetime.now(timezone.utc).isoformat()
    payload = {
        "device_id": "ESP-TZ",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 1000,
        "ts_utc": aware,
    }
    ev = EventPayload.model_validate(payload)
    assert ev.ts_utc.tzinfo is None
