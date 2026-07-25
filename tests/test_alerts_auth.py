"""Autenticacao e autoria nas acoes de alerta (reconhecer / concluir).

Este arquivo escrevia no banco REAL: importava DB_PATH de interface.api_shared
(que aponta para o dados.db do diretorio de trabalho, ou /data/dados.db no
container), criava o usuario "nurse_joy" e alertas de teste ali, e construia o
TestClient no escopo do modulo — antes de qualquer fixture poder trocar o
banco. O `except ValueError: pass` na criacao do usuario era justamente para
tolerar a linha deixada por uma execucao anterior.

Agora usa a fixture `app_isolado` (tests/conftest.py), que liga a app a um
banco temporario por teste.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from interface.auth_utils import create_access_token

ALERTA_ID = "PAC-TEST-AUTH__2025-01-01T10:00:00"


@pytest.fixture
def ambiente(app_isolado):
    """Cria usuario e alerta no banco temporario deste teste."""
    from interface.dao import criar_usuario, inserir_alertas

    db = app_isolado.db_path
    criar_usuario(db, "nurse_joy", "hashed_password", "Nurse Joy")
    inserir_alertas(db, [{
        "paciente_id": "PAC-TEST-AUTH",
        "inicio": "2025-01-01T10:00:00",
        "fim": "2025-01-01T10:30:00",
        "tipo": "imobilidade",
        "perfil": "medio",
        "janela_min": 120,
        "status": "aberto",
        "duracao_min": 30,
    }])
    return app_isolado


def _timeline(db_path: str):
    from interface.dao import selecionar_timeline

    return selecionar_timeline(db_path, paciente_id="PAC-TEST-AUTH")


def test_acknowledge_requires_auth(ambiente):
    with TestClient(ambiente.app) as client:
        resp = client.post(f"/api/frontend/alerts/{ALERTA_ID}/acknowledge")
    assert resp.status_code == 401


def test_acknowledge_records_user(ambiente):
    token = create_access_token({"sub": "nurse_joy"})
    with TestClient(ambiente.app) as client:
        resp = client.post(
            f"/api/frontend/alerts/{ALERTA_ID}/acknowledge",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text

    evento = next((e for e in _timeline(ambiente.db_path) if e["tipo"] == "alert_ack"), None)
    assert evento is not None
    assert "nurse_joy" in evento["descricao"]
    assert evento["meta"]["user"] == "nurse_joy"


def test_complete_records_user(ambiente):
    with sqlite3.connect(ambiente.db_path) as conn:
        conn.execute("UPDATE alertas SET status = 'aberto' WHERE paciente_id = 'PAC-TEST-AUTH'")

    token = create_access_token({"sub": "nurse_joy"})
    with TestClient(ambiente.app) as client:
        resp = client.post(
            f"/api/frontend/alerts/{ALERTA_ID}/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text

    evento = next((e for e in _timeline(ambiente.db_path) if e["tipo"] == "alert_close"), None)
    assert evento is not None
    assert "nurse_joy" in evento["descricao"]
    assert evento["meta"]["user"] == "nurse_joy"
