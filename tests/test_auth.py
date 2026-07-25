from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import recarregar_app


@pytest.fixture
def make_app(tmp_path: Path, monkeypatch):
    """Constroi a app com um banco temporario.

    Antes este helper escrevia direto em os.environ e nunca restaurava, entao
    UPP_DB_PATH e UPP_ADMIN_PASS vazavam para os arquivos seguintes da suite —
    era a causa de test_admin_import_endpoint.py passar isolado e falhar junto.
    Com monkeypatch o ambiente volta ao normal ao fim de cada teste.
    """

    def _make(env_pass: str | None = None, env_user: str | None = None):
        monkeypatch.setenv("UPP_DB_PATH", str(tmp_path / "test_auth.db"))
        for nome, valor in (("UPP_ADMIN_PASS", env_pass), ("UPP_ADMIN_USER", env_user)):
            if valor is None:
                monkeypatch.delenv(nome, raising=False)
            else:
                monkeypatch.setenv(nome, valor)
        return recarregar_app().app

    return _make


def test_register_and_login_success(make_app):
    app = make_app()
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


def test_register_duplicate(make_app):
    app = make_app()
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"username": "bob", "password": "pw"})
        assert r.status_code == 201
        # Reusa a sessao criada no cadastro acima (o cadastro ja nao e aberto).
        r2 = client.post("/api/auth/register", json={"username": "bob", "password": "pw2"})
        assert r2.status_code == 400


def test_primeiro_cadastro_e_liberado_depois_exige_credencial(make_app):
    """Cadastro aberto anularia toda a autenticacao das rotas clinicas: bastaria
    criar uma conta para ver os pacientes. A primeira conta e liberada (bootstrap
    da instalacao); a partir dai exige sessao ou token de convite."""
    app = make_app()
    with TestClient(app) as bootstrap:
        r = bootstrap.post("/api/auth/register", json={"username": "primeiro", "password": "pw"})
        assert r.status_code == 201, "primeiro cadastro deveria ser liberado"

    # Cliente novo, sem cookie de sessao.
    with TestClient(app) as anonimo:
        r = anonimo.post("/api/auth/register", json={"username": "invasor", "password": "pw"})
        assert r.status_code == 403, f"cadastro anonimo foi aceito: {r.text}"
        assert r.json()["detail"]["code"] == "cadastro_restrito"


def test_cadastro_aceita_token_de_convite(make_app, monkeypatch):
    monkeypatch.setenv("UPP_REGISTER_TOKEN", "convite-secreto")
    app = make_app()
    with TestClient(app) as c:
        assert c.post("/api/auth/register", json={"username": "primeiro", "password": "pw"}).status_code == 201

    with TestClient(app) as anonimo:
        r = anonimo.post(
            "/api/auth/register",
            json={"username": "convidado", "password": "pw"},
            headers={"X-Register-Token": "convite-secreto"},
        )
        assert r.status_code == 201, f"token de convite valido foi recusado: {r.text}"

    with TestClient(app) as anonimo:
        r = anonimo.post(
            "/api/auth/register",
            json={"username": "outro", "password": "pw"},
            headers={"X-Register-Token": "errado"},
        )
        assert r.status_code == 403


def test_login_wrong_password(make_app):
    app = make_app()
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"username": "carol", "password": "goodpass"})
        assert r.status_code == 201
        r2 = client.post("/api/auth/login", json={"username": "carol", "password": "bad"})
        assert r2.status_code == 401


def test_login_env_fallback(make_app, monkeypatch):
    """O fallback por env vale apenas para o usuario admin configurado."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    app = make_app(env_pass="envsecret", env_user="admin")
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "envsecret"})
        assert r.status_code == 200
        assert r.json().get("username") == "admin"


def test_login_env_fallback_rejeita_username_arbitrario(make_app, monkeypatch):
    """UPP_ADMIN_PASS nao pode autenticar um username qualquer.

    Este ramo do login so roda quando o usuario NAO existe no banco. Antes
    bastava a senha bater, entao qualquer nome inventado virava um JWT valido
    com aquele `sub` — o atacante escolhia a identidade que quisesse. A versao
    antiga deste teste afirmava justamente isso como comportamento correto.

    Roda em development de proposito: e o unico ambiente onde o fallback
    existe, entao e onde o bypass precisa ser provado fechado.
    """
    monkeypatch.setenv("ENVIRONMENT", "development")
    app = make_app(env_pass="envsecret", env_user="admin")
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "noone", "password": "envsecret"})
        assert r.status_code == 401, (
            f"username arbitrario foi autenticado com UPP_ADMIN_PASS: {r.text}"
        )


def test_login_env_fallback_desabilitado_em_producao(make_app, monkeypatch):
    """Em producao a autenticacao tem que passar pelo banco."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    app = make_app(env_pass="envsecret", env_user="admin")
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "envsecret"})
        assert r.status_code == 401, f"fallback de dev ativo em producao: {r.text}"


def test_cookie_de_sessao_tem_samesite(make_app):
    """Sem SameSite, com allow_credentials=True no CORS, todo endpoint que muda
    estado fica exposto a CSRF."""
    app = make_app()
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"username": "dave", "password": "pw"})
        assert r.status_code == 201
        set_cookie = r.headers.get("set-cookie", "")
        assert "access_token" in set_cookie
        assert "samesite=lax" in set_cookie.lower(), f"cookie sem SameSite: {set_cookie}"
        assert "httponly" in set_cookie.lower()
        # cookie forjavel legado nao deve mais ser emitido
        assert "session_user=" not in set_cookie, f"session_user voltou a ser emitido: {set_cookie}"


def test_cookie_secure_segue_o_protocolo_da_requisicao(make_app):
    """Secure precisa vir do protocolo, nao de ENVIRONMENT.

    O container roda com ENVIRONMENT=production e ainda publica a porta 8000 em
    HTTP para debug. Se Secure fosse ligado por ambiente, o browser descartaria
    o cookie nesse acesso e o login simplesmente nao funcionaria.
    """
    app = make_app()
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"username": "erin", "password": "pw"})
        assert r.status_code == 201
        assert "secure" not in r.headers.get("set-cookie", "").lower(), (
            "cookie marcado como Secure numa requisicao HTTP — o browser o descartaria"
        )

        # Atras do Caddy (TLS terminado no proxy) o header indica HTTPS.
        r2 = client.post(
            "/api/auth/login",
            json={"username": "erin", "password": "pw"},
            headers={"X-Forwarded-Proto": "https"},
        )
        assert r2.status_code == 200
        assert "secure" in r2.headers.get("set-cookie", "").lower(), (
            "cookie sem Secure mesmo com X-Forwarded-Proto: https"
        )
