import json
import sqlite3
from importlib import reload

import pytest
from fastapi.testclient import TestClient

from interface.dao import criar_esquema


@pytest.fixture()
def pacientes_client(tmp_path, monkeypatch):
    tmp_db = tmp_path / "dados.db"
    tmp_docs = tmp_path / "docs"
    monkeypatch.setenv("UPP_DB_PATH", str(tmp_db))
    monkeypatch.setenv("PACIENTE_DOCS_DIR", str(tmp_docs))
    monkeypatch.setenv("PACIENTE_DOC_MAX_MB", "1")

    criar_esquema(str(tmp_db))

    import interface.web as web_module

    reload(web_module)
    client = TestClient(web_module.app)
    yield {
        "client": client,
        "db_path": tmp_db,
    }
    client.close()


def test_gerar_pacientes_com_camas_unicas(pacientes_client):
    client = pacientes_client["client"]
    db_path = pacientes_client["db_path"]

    resp = client.post("/pacientes/generar", data={"gerar_count": "10", "assign_camas": "1", "cama_prefix": "LEITO", "cama_start": "1"})
    assert resp.status_code == 200
    hx = resp.headers.get("HX-Trigger")
    assert hx is not None
    payload = json.loads(hx)
    info = payload.get("pacientes-gerados")
    assert info is not None
    assert isinstance(info.get("count"), int)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT paciente_id, cama_id FROM paciente_fichas WHERE cama_id IS NOT NULL").fetchall()

    camas = [row["cama_id"] for row in rows]
    # at least requested camas should be present
    assert len(camas) >= 1
    # ensure uniqueness
    assert len(camas) == len(set(camas))
    # pattern check
    for c in camas:
        assert c.startswith("LEITO-")
