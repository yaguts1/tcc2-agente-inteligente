"""Contract tests to ensure backend and frontend agree on API shapes.

These tests are intended to fail if the backend changes fields or types
expected by the frontend or by device firmware (ESP32).
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

import interface.api as api_mod
from interface.dao import criar_esquema, inserir_alertas
from interface.api import EventPayload


@pytest.mark.asyncio
async def test_frontend_alerts_shape_matches_contract(tmp_path):
    db_path = tmp_path / "dados.db"
    criar_esquema(db_path)
    # point the API module to the temp DB for this test
    api_mod.DB_PATH = str(db_path)

    # insert a sample alerta
    now = datetime.now().replace(microsecond=0)
    inicio = now.strftime("%Y-%m-%dT%H:%M:%S")
    alert = {
        "paciente_id": "CT-1",
        "inicio": inicio,
        "fim": None,
        "tipo": "imobilidade",
        "perfil": "alto",
        "janela_min": 60,
        "status": "aberto",
        "duracao_min": None,
    }
    assert inserir_alertas(str(db_path), [alert]) == 1

    # call the route function directly (it's async)
    results = await api_mod.frontend_alerts(horas=24)
    assert isinstance(results, list)
    assert len(results) >= 1
    r = results[0]

    # required keys and their rough types
    expected_keys = {
        "id": str,
        "patientName": str,
        "room": str,
        "bed": str,
        "lastRepositioning": str,
        "nextRepositioning": str,
        "riskLevel": str,
        "status": str,
    }

    for k, t in expected_keys.items():
        assert k in r, f"Missing key {k} in frontend alert"
        assert isinstance(r[k], t) or r[k] is None


def test_eventpayload_accepts_esp32_like_payload():
    # This mimics the ESP32 JSON that will be posted to /eventos
    payload = {
        "device_id": "ESP32-01",
        "paciente_id": "CT-1",
        "cama_id": "201A / Leito 1",
        "postura": "supino",
        "confianca": 0.95,
        "amostra_ms": 60000,
        # ISO string should be accepted and normalized by the validator
        "ts_utc": datetime.utcnow().isoformat(),
        "pressao_pico": None,
    }

    ev = EventPayload.model_validate(payload)
    assert ev.device_id == "ESP32-01"
    assert ev.postura == "supino"
    assert isinstance(ev.ts_utc, datetime)
