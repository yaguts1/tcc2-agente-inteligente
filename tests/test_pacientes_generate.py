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
        "docs_dir": tmp_docs,
    }
    client.close()


def test_gerar_pacientes_e_listar(pacientes_client):
    client = pacientes_client["client"]
    db_path = pacientes_client["db_path"]

    resp = client.post("/pacientes/generar", data={"gerar_count": "5"})
    assert resp.status_code == 200
    hx = resp.headers.get("HX-Trigger")
    assert hx is not None
    payload = json.loads(hx)
    info = payload.get("pacientes-gerados")
    assert info is not None
    assert isinstance(info.get("count"), int)
    assert info.get("count") >= 1

    # check API listing
    api = client.get("/api/pacientes")
    assert api.status_code == 200
    data = api.json()
    assert isinstance(data, list)

    # verify DB rows
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM paciente_fichas")
        total_db = cur.fetchone()[0]

    assert total_db >= info.get("count")
