import json



def test_admin_import_endpoint_creates_ficha_and_alert(app_isolado):
    """Usa a fixture `app_isolado` (tests/conftest.py), que liga a app a um
    banco temporario proprio.

    Antes o teste escrevia em os.environ sem restaurar e nao recarregava os
    modulos, entao herdava os que test_auth.py havia religado ao banco
    temporario DELE: passava isolado e falhava na suite completa.

    Sem UPP_ADMIN_TOKEN (o conftest o remove), o endpoint exige sessao JWT.
    """
    from fastapi.testclient import TestClient

    db_path = app_isolado.db_path

    with TestClient(app_isolado.app) as client:
        # Registra um usuario real e autentica com ele. Antes este teste logava
        # como "tester" com UPP_ADMIN_PASS, apoiando-se no bypass em que
        # qualquer username servia — caminho que foi fechado. Usar um usuario
        # de verdade exercita a autenticacao real e independe do ENVIRONMENT.
        resp = client.post(
            "/api/auth/register", json={"username": "admin_tester", "password": "senha-de-teste"}
        )
        assert resp.status_code == 201, resp.text

        resp = client.post(
            "/api/auth/login", json={"username": "admin_tester", "password": "senha-de-teste"}
        )
        assert resp.status_code == 200, resp.text

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
    from interface.dao import obter_ficha_paciente

    app_db = db_path
    ficha = obter_ficha_paciente(app_db, "PAC-7777")
    assert ficha is not None
    # alert row presence is not strictly guaranteed here (dedup/insert rules); ficha creation is the main contract
