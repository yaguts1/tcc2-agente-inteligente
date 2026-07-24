"""Tests for the admin import helper which imports alert dicts into the DB."""
from __future__ import annotations

from datetime import datetime

from interface.routers.admin import import_alerts_list
from interface.dao import criar_esquema, selecionar_alertas_janela


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def test_import_alerts_list_inserts_alerts(tmp_path) -> None:
    db_path = tmp_path / "dados.db"
    criar_esquema(db_path)

    now = datetime.now()
    alerts = [
        {
            "paciente_id": "IMP-1",
            "inicio": _iso(now),
            "tipo": "imobilidade",
            "perfil": "medio",
            "janela_min": 60,
            "status": "aberto",
        }
    ]

    inserted = import_alerts_list(alerts, db_path=str(db_path))
    assert inserted == 1

    results = selecionar_alertas_janela(str(db_path), horas=24)
    assert any(r.get("paciente_id") == "IMP-1" for r in results)
