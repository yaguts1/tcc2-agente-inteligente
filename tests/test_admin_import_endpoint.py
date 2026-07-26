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
        # `tipo` precisa ser um dos aceitos pelo CHECK da tabela. Este teste
        # mandava "sensor", que a importacao descartava em silencio por causa do
        # `INSERT OR IGNORE` — e o proprio teste sacramentava isso, afirmando
        # apenas que `inserted is not None` e comentando que "a presenca do
        # alerta nao e estritamente garantida". Nao era dedup: o alerta nunca
        # chegava ao banco, e quem importasse um arquivo inteiro receberia
        # `ok: true` sem nenhum registro gravado.
        rec = {
            "paciente_id": "PAC-7777",
            "inicio": "2025-10-25T09:00:00",
            "tipo": "imobilidade",
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
    assert body.get("received") == 1
    assert body.get("inserted") == 1, (
        f"a importacao respondeu ok mas gravou {body.get('inserted')} de 1 alerta"
    )

    # verify ficha exists (ensure_minimal_paciente_ficha should have created it)
    import sqlite3

    from interface.dao import obter_ficha_paciente

    app_db = db_path
    ficha = obter_ficha_paciente(app_db, "PAC-7777")
    assert ficha is not None

    with sqlite3.connect(app_db) as conn:
        linhas = conn.execute(
            "SELECT inicio, tipo, status FROM alertas WHERE paciente_id = 'PAC-7777'"
        ).fetchall()
    assert linhas == [("2025-10-25T09:00:00", "imobilidade", "aberto")]


def test_import_rejeita_alerta_invalido(app_isolado):
    """Importar dado que o esquema recusa tem de FALHAR, e dizer por que.

    Descartar em silencio e o pior desfecho para uma importacao: o operador ve
    "ok" e acredita que o historico foi carregado.
    """
    from fastapi.testclient import TestClient

    with TestClient(app_isolado.app) as client:
        client.post("/api/auth/register", json={"username": "imp", "password": "senha-de-teste"})
        client.post("/api/auth/login", json={"username": "imp", "password": "senha-de-teste"})

        rec = {
            "paciente_id": "PAC-8888",
            "inicio": "2025-10-25T09:00:00",
            "tipo": "sensor",
            "perfil": "medio",
            "janela_min": 30,
            "status": "aberto",
        }
        resp = client.post(
            "/api/admin/import_alerts",
            files={"arquivo": ("a.jsonl", json.dumps(rec) + "\n", "application/jsonl")},
        )

    assert resp.status_code == 400, resp.text
    assert "tipo" in resp.text
