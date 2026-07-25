"""Contrato de datas nas duas fronteiras do sistema.

Sao regras OPOSTAS, e de proposito:

- ENTRADA (EventPayload, vindo do ESP32): normaliza para UTC naive, que e a
  convencao interna de armazenamento (ver interface/tempo.py).
- SAIDA (API para o browser): emite ISO-8601 COM offset explicito. Sem ele,
  `new Date("2026-07-25T13:44:47")` interpreta a string como hora LOCAL, e para
  um usuario no Brasil (UTC-3) todo horario aparecia 3h adiantado — inclusive o
  do proximo reposicionamento, que e o numero que a equipe usa para decidir
  quando virar o paciente.

A versao anterior deste arquivo exigia naive TAMBEM na saida, ou seja,
travava o defeito como se fosse o contrato correto.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import interface.api as api_mod
import interface.api_shared as api_shared
import interface.services.alerts_service as alerts_service
import interface.routers.alerts as alerts_router
from importlib import reload
from interface.dao import criar_esquema, inserir_alertas
from interface.schemas import EventPayload


@pytest.mark.asyncio
async def test_frontend_alerts_datetimes_tem_offset(tmp_path, monkeypatch):
    db_path = tmp_path / "dados.db"
    criar_esquema(db_path)

    monkeypatch.setenv("UPP_DB_PATH", str(db_path))
    reload(api_shared)
    reload(alerts_service)
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
        for campo in ("lastRepositioning", "nextRepositioning"):
            valor = r.get(campo)
            if valor is None:
                continue
            parsed = datetime.fromisoformat(valor)
            assert parsed.tzinfo is not None, (
                f"{campo} precisa levar offset explicito, veio naive: {valor}. "
                "Sem offset, `new Date(str)` no browser interpreta a string como "
                "hora LOCAL — para um usuario no Brasil todo horario aparecia 3h "
                "adiantado, incluindo o do proximo reposicionamento."
            )


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
