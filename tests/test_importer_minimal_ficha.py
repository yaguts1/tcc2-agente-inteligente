import json
from pathlib import Path

import pytest


def test_importer_creates_minimal_ficha_and_alert(tmp_path):
    # prepare DB path
    db_path = tmp_path / "test.db"

    # create schema
    from interface.dao import criar_esquema, selecionar_alertas_janela, obter_ficha_paciente

    criar_esquema(str(db_path))

    # create a small JSONL file with frontend-shaped alert
    alerts_file = tmp_path / "alerts.jsonl"
    rec = {
        "patientName": "PAC-9999",
        "lastRepositioning": "2025-10-25T12:00:00",
        "nextRepositioning": "2025-10-25T12:30:00",
        "riskLevel": "medium",
        "status": "pending",
    }
    alerts_file.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")

    # run importer main
    from scripts import import_alerts

    rc = import_alerts.main(["--input", str(alerts_file), "--db-path", str(db_path), "--commit"])
    assert rc == 0

    # verify ficha created
    ficha = obter_ficha_paciente(str(db_path), "PAC-9999")
    assert ficha is not None
    assert ficha.get("paciente_id") == "PAC-9999"

    # verify alert inserted
    alerts = selecionar_alertas_janela(str(db_path), horas=None)
    assert len(alerts) == 1
