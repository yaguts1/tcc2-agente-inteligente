"""Tests for FastAPI UI using virtual now parameter."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from importlib import reload
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interface.dao import criar_esquema


@pytest.fixture()
def ui_client(tmp_path, monkeypatch):
    tmp_db = tmp_path / "dados.db"
    monkeypatch.setenv("UPP_DB_PATH", str(tmp_db))
    criar_esquema(str(tmp_db))

    now_dt = datetime.now().replace(microsecond=0)
    past_dt = now_dt - timedelta(minutes=10)
    future_dt = now_dt + timedelta(minutes=5)

    with sqlite3.connect(tmp_db) as conn:
        conn.execute("INSERT OR REPLACE INTO pacientes(id) VALUES (?)", ("P_TST",))
        conn.execute(
            "INSERT INTO alertas (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "P_TST",
                past_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                None,
                "imobilidade",
                "alto",
                60,
                "aberto",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO alertas (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "P_TST",
                future_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                None,
                "imobilidade",
                "alto",
                60,
                "aberto",
                None,
            ),
        )
        conn.commit()

    import interface.web as web_module

    reload(web_module)
    client = TestClient(web_module.app)
    data = {
        "client": client,
        "db_path": tmp_db,
        "now_dt": now_dt,
        "now_iso": now_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "now_plus_2_iso": (now_dt + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        "now_plus_6_iso": (now_dt + timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%S"),
        "past_iso": past_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "future_iso": future_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    yield data
    client.close()


def _fetch_alert(conn: sqlite3.Connection, inicio: str) -> sqlite3.Row | None:
    cursor = conn.execute(
        "SELECT paciente_id, inicio, fim, status, duracao_min FROM alertas WHERE paciente_id = ? AND inicio = ?",
        ("P_TST", inicio),
    )
    return cursor.fetchone()


def test_alertas_virtual_now_filter(ui_client):
    client = ui_client["client"]
    now_iso = ui_client["now_iso"]
    future_iso = ui_client["future_iso"]
    past_iso = ui_client["past_iso"]

    resp = client.get(f"/partials/alertas?now={now_iso}")
    assert resp.status_code == 200
    assert past_iso in resp.text
    assert future_iso not in resp.text

    resp2 = client.get(f"/partials/alertas?now={ui_client['now_plus_6_iso']}")
    assert resp2.status_code == 200
    assert future_iso in resp2.text


def test_encerrar_usa_relugio_virtual(ui_client):
    client = ui_client["client"]
    now_plus_2 = ui_client["now_plus_2_iso"]
    past_iso = ui_client["past_iso"]

    resp = client.post(f"/alertas/P_TST/{past_iso}/encerrar", params={"now": now_plus_2})
    assert resp.status_code == 200

    resp_check = client.get(f"/partials/alertas?now={now_plus_2}")
    assert past_iso not in resp_check.text

    with sqlite3.connect(ui_client["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        row = _fetch_alert(conn, past_iso)
    assert row is not None
    assert row["status"] == "fechado"
    assert row["fim"] == now_plus_2
    assert 11.9 <= float(row["duracao_min"]) <= 12.1


def test_timeline_cursor_alinha_com_now(ui_client):
    client = ui_client["client"]
    now_iso = ui_client["now_iso"]
    now_plus_6 = ui_client["now_plus_6_iso"]

    resp = client.get(f"/partials/timeline?now={now_iso}")
    assert resp.status_code == 200
    html_now = resp.text
    assert "cursor" in html_now
    assert "segment" in html_now

    resp2 = client.get(f"/partials/timeline?now={now_plus_6}")
    assert resp2.status_code == 200
    html_future = resp2.text
    assert html_future != html_now


def test_reconhecer_mantem_alerta_visivel(ui_client):
    client = ui_client["client"]
    future_iso = ui_client["future_iso"]
    now_plus_6 = ui_client["now_plus_6_iso"]

    resp = client.post(
        f"/alertas/P_TST/{future_iso}/reconhecer",
        params={"now": now_plus_6},
    )
    assert resp.status_code == 200

    with sqlite3.connect(ui_client["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        row = _fetch_alert(conn, future_iso)
    assert row is not None
    assert row["status"] == "reconhecido"

    resp_check = client.get(f"/partials/alertas?now={now_plus_6}")
    assert future_iso in resp_check.text
    assert "reconhecido" in resp_check.text
