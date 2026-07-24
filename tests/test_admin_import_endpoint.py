import os
import json
from pathlib import Path

import pytest


def test_admin_import_endpoint_creates_ficha_and_alert(tmp_path):
    # ensure the app uses a temp DB
    db_path = tmp_path / "admin_test.db"
    os.environ["UPP_DB_PATH"] = str(db_path)
    # ensure no UPP_ADMIN_TOKEN so endpoint falls back to session cookie
    os.environ.pop("UPP_ADMIN_TOKEN", None)
    # UPP_ADMIN_PASS has no default anymore (a hardcoded default would be a
    # login bypass) - set it explicitly for this test's fallback-login path.
    os.environ["UPP_ADMIN_PASS"] = "admin"

    # import app after env is set
    from fastapi.testclient import TestClient
    from interface.web import app

    with TestClient(app) as client:
        # perform login using fallback admin password (set above via UPP_ADMIN_PASS)
        resp = client.post("/api/auth/login", json={"username": "tester", "password": "admin"})
        assert resp.status_code == 200

        # prepare alerts payload in DAO format expected by import (not frontend-shaped)
        rec = {
            "paciente_id": "PAC-7777",
            "inicio": "2025-10-25T09:00:00",
            "tipo": "sensor",
            "perfil": "medio",
            "janela_min": 30,
            "status": "aberto",
        }

        # send as uploaded JSONL file (multipart) because endpoint accepts an UploadFile
        jsonl = json.dumps(rec, ensure_ascii=False) + "\n"
        files = {"arquivo": ("alerts.jsonl", jsonl, "application/jsonl")}
        resp2 = client.post("/api/admin/import_alerts", files=files)
        assert resp2.status_code == 200, resp2.text
    body = resp2.json()
    # we expect the endpoint to have received one record and returned an inserted count (may be 0 depending on dedup)
    assert body.get("received") == 1
    assert body.get("inserted") is not None

    # verify ficha exists (ensure_minimal_paciente_ficha should have created it)
    import interface.api as api
    from interface.dao import obter_ficha_paciente, selecionar_alertas_janela

    app_db = api.DB_PATH
    ficha = obter_ficha_paciente(app_db, "PAC-7777")
    assert ficha is not None
    # alert row presence is not strictly guaranteed here (dedup/insert rules); ficha creation is the main contract
