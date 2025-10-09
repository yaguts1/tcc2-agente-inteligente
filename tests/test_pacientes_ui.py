import json
import sqlite3
from importlib import reload
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interface.dao import criar_esquema, criar_paciente


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


def test_pacientes_index_page(pacientes_client):
    client = pacientes_client["client"]

    resp = client.get("/pacientes")
    assert resp.status_code == 200
    assert "Fichas de Pacientes" in resp.text


def test_paciente_criacao_com_rotina_padrao(pacientes_client):
    client = pacientes_client["client"]
    resp = client.post(
        "/pacientes/salvar",
        data={
            "nome": "Paciente Teste",
            "perfil": "medio",
            "observacoes": "Obs",
            "usar_rotinas_padrao": "1",
        },
    )
    assert resp.status_code == 200
    assert "Ficha salva com sucesso" in resp.text

    hx_header = resp.headers.get("HX-Trigger")
    assert hx_header is not None
    evento = json.loads(hx_header)
    paciente_id = evento["paciente-atualizado"]["paciente_id"]

    with sqlite3.connect(pacientes_client["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        ficha = conn.execute(
            "SELECT nome, perfil, observacoes FROM paciente_fichas WHERE paciente_id = ?",
            (paciente_id,),
        ).fetchone()
        rotinas_total = conn.execute(
            "SELECT COUNT(*) FROM paciente_rotinas WHERE paciente_id = ?",
            (paciente_id,),
        ).fetchone()[0]

    assert ficha is not None
    assert ficha["nome"] == "Paciente Teste"
    assert ficha["perfil"] == "medio"
    assert rotinas_total == 4

    lista = client.get("/partials/pacientes/lista")
    assert lista.status_code == 200
    assert "Paciente Teste" in lista.text


def test_rotina_linha_endpoint(pacientes_client):
    client = pacientes_client["client"]
    resp = client.get("/pacientes/rotinas/linha", params={"index": 5})
    assert resp.status_code == 200
    assert "name=\"rotinas-5-label\"" in resp.text


def test_documentos_upload_e_remocao(pacientes_client):
    client = pacientes_client["client"]
    docs_dir = pacientes_client["docs_dir"]

    ficha = criar_paciente(
        str(pacientes_client["db_path"]),
        nome="Paciente Documentos",
        perfil="medio",
        observacoes="",
        rotinas=None,
    )
    paciente_id = ficha["paciente_id"]

    upload = client.post(
        f"/pacientes/{paciente_id}/documentos",
        data={"observacao": "relatorio"},
        files={"arquivo": ("relatorio.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert upload.status_code == 200
    hx_upload = upload.headers.get("HX-Trigger")
    assert hx_upload is not None

    with sqlite3.connect(pacientes_client["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        documento = conn.execute(
            "SELECT id, caminho, nome_arquivo FROM paciente_documentos WHERE paciente_id = ?",
            (paciente_id,),
        ).fetchone()

    assert documento is not None
    documento_id = documento["id"]
    caminho_relativo = Path(documento["caminho"]) if documento["caminho"] else None
    if caminho_relativo and not caminho_relativo.is_absolute():
        arquivo_path = docs_dir / caminho_relativo
    else:
        arquivo_path = Path(documento["caminho"])
    assert arquivo_path.exists()

    download = client.get(f"/pacientes/documentos/{documento_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")

    remover = client.delete(f"/pacientes/documentos/{documento_id}")
    assert remover.status_code == 200
    hx_delete = remover.headers.get("HX-Trigger")
    assert hx_delete is not None
    assert not arquivo_path.exists()
