import os
from pathlib import Path
from fastapi.testclient import TestClient
import importlib


def _make_app_with_db(tmp_path: Path, env_pass: str | None = None):
    db_path = tmp_path / "test_auth.db"
    # ensure fresh environment for import-time DB_PATH resolution
    os.environ["UPP_DB_PATH"] = str(db_path)
    if env_pass is not None:
        os.environ["UPP_ADMIN_PASS"] = env_pass
    else:
        os.environ.pop("UPP_ADMIN_PASS", None)
    # import interface.web after env var set so DB_PATH is bound correctly
    import interface.web as web
    import interface.api as api
    importlib.reload(api)
    importlib.reload(web)
    # Reset rate limiting for tests
    api._reset_auth_rate_limits()
    return web.app


def test_register_and_login_success(tmp_path: Path):
    app = _make_app_with_db(tmp_path)
    with TestClient(app) as client:
        # register
        r = client.post("/api/auth/register", json={"username": "alice", "password": "secret"})
        assert r.status_code == 201, r.text
        assert r.json().get("username") == "alice"

        # login should succeed (we'll log out first to ensure independent flow)
        client.post("/api/auth/logout")
        r2 = client.post("/api/auth/login", json={"username": "alice", "password": "secret"})
        assert r2.status_code == 200
        assert r2.json().get("username") == "alice"


def test_register_duplicate(tmp_path: Path):
    app = _make_app_with_db(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"username": "bob", "password": "pw"})
        assert r.status_code == 201
        r2 = client.post("/api/auth/register", json={"username": "bob", "password": "pw2"})
        assert r2.status_code == 400


def test_login_wrong_password(tmp_path: Path):
    app = _make_app_with_db(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"username": "carol", "password": "goodpass"})
        assert r.status_code == 201
        r2 = client.post("/api/auth/login", json={"username": "carol", "password": "bad"})
        assert r2.status_code == 401


def test_login_env_fallback(tmp_path: Path):
    # do not create a DB user; rely on UPP_ADMIN_PASS fallback
    app = _make_app_with_db(tmp_path, env_pass="envsecret")
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "noone", "password": "envsecret"})
        assert r.status_code == 200
        assert r.json().get("username") == "noone"
