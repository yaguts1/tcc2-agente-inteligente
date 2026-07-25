import os
from pathlib import Path
from fastapi.testclient import TestClient
import importlib


def _make_app_with_db(tmp_path: Path, env_pass: str | None = None, env_user: str | None = None):
    db_path = tmp_path / "test_auth.db"
    # ensure fresh environment for import-time DB_PATH resolution
    os.environ["UPP_DB_PATH"] = str(db_path)
    if env_pass is not None:
        os.environ["UPP_ADMIN_PASS"] = env_pass
    else:
        os.environ.pop("UPP_ADMIN_PASS", None)
    if env_user is not None:
        os.environ["UPP_ADMIN_USER"] = env_user
    else:
        os.environ.pop("UPP_ADMIN_USER", None)
    # import interface.web after env var set so DB_PATH is bound correctly
    import interface.api_shared as api_shared
    import interface.routers.auth as auth_router
    import interface.web as web
    import interface.api as api
    importlib.reload(api_shared)
    importlib.reload(auth_router)
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


def test_login_env_fallback(tmp_path: Path, monkeypatch):
    """O fallback por env vale apenas para o usuario admin configurado."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    app = _make_app_with_db(tmp_path, env_pass="envsecret", env_user="admin")
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "envsecret"})
        assert r.status_code == 200
        assert r.json().get("username") == "admin"


def test_login_env_fallback_rejeita_username_arbitrario(tmp_path: Path, monkeypatch):
    """UPP_ADMIN_PASS nao pode autenticar um username qualquer.

    Este ramo do login so roda quando o usuario NAO existe no banco. Antes
    bastava a senha bater, entao qualquer nome inventado virava um JWT valido
    com aquele `sub` — o atacante escolhia a identidade que quisesse. A versao
    antiga deste teste afirmava justamente isso como comportamento correto.

    Roda em development de proposito: e o unico ambiente onde o fallback
    existe, entao e onde o bypass precisa ser provado fechado.
    """
    monkeypatch.setenv("ENVIRONMENT", "development")
    app = _make_app_with_db(tmp_path, env_pass="envsecret", env_user="admin")
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "noone", "password": "envsecret"})
        assert r.status_code == 401, (
            f"username arbitrario foi autenticado com UPP_ADMIN_PASS: {r.text}"
        )


def test_login_env_fallback_desabilitado_em_producao(tmp_path: Path, monkeypatch):
    """Em producao a autenticacao tem que passar pelo banco."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    app = _make_app_with_db(tmp_path, env_pass="envsecret", env_user="admin")
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "envsecret"})
        assert r.status_code == 401, f"fallback de dev ativo em producao: {r.text}"


def test_cookie_de_sessao_tem_samesite(tmp_path: Path):
    """Sem SameSite, com allow_credentials=True no CORS, todo endpoint que muda
    estado fica exposto a CSRF."""
    app = _make_app_with_db(tmp_path)
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"username": "dave", "password": "pw"})
        assert r.status_code == 201
        set_cookie = r.headers.get("set-cookie", "")
        assert "access_token" in set_cookie
        assert "samesite=lax" in set_cookie.lower(), f"cookie sem SameSite: {set_cookie}"
        assert "httponly" in set_cookie.lower()
        # cookie forjavel legado nao deve mais ser emitido
        assert "session_user=" not in set_cookie, f"session_user voltou a ser emitido: {set_cookie}"
