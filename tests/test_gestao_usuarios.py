"""Gestao de usuarios.

Nao havia nenhuma: dava para criar contas, mas nao para listar, promover,
desativar ou trocar senha. Numa instalacao real isso significa que quem sai da
equipe mantem acesso indefinidamente, e que nao ha como criar um segundo
administrador — perdida a unica conta admin, as operacoes administrativas
ficariam inacessiveis para sempre.
"""

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def equipe(app_isolado):
    """Admin (bootstrap) + um staff."""
    client = TestClient(app_isolado.app)

    r_admin = client.post("/api/auth/register", json={"username": "chefe", "password": "senha-inicial"})
    assert r_admin.status_code == 201, r_admin.text
    admin = {"Authorization": f"Bearer {r_admin.json()['token']}"}

    r_staff = client.post(
        "/api/auth/register",
        json={"username": "tecnico", "password": "senha-inicial"},
        headers=admin,
    )
    assert r_staff.status_code == 201, r_staff.text
    client.cookies.clear()

    return {
        "client": client,
        "db": app_isolado.db_path,
        "admin": admin,
        "staff": {"Authorization": f"Bearer {r_staff.json()['token']}"},
    }


def test_listar_usuarios_nao_expoe_hash(equipe):
    c = equipe["client"]
    resp = c.get("/api/usuarios", headers=equipe["admin"])
    assert resp.status_code == 200

    usuarios = resp.json()
    assert {u["username"] for u in usuarios} == {"chefe", "tecnico"}
    for u in usuarios:
        assert "password_hash" not in u, f"hash de senha vazou na listagem: {u}"


def test_staff_nao_gerencia_usuarios(equipe):
    c = equipe["client"]
    c.cookies.clear()
    assert c.get("/api/usuarios", headers=equipe["staff"]).status_code == 403


def test_promover_e_rebaixar(equipe):
    c = equipe["client"]
    c.cookies.clear()

    r = c.patch("/api/usuarios/tecnico/papel", json={"role": "admin"}, headers=equipe["admin"])
    assert r.status_code == 200, r.text

    # O papel viaja no JWT: a sessao antiga precisa cair, senao o usuario
    # continuaria operando com o papel anterior ate o token expirar.
    c.cookies.clear()
    assert c.get("/api/usuarios", headers=equipe["staff"]).status_code == 401

    # O corte de revogacao e o proximo segundo (o `iat` do JWT tem resolucao de
    # 1s), entao um login feito no MESMO segundo tambem cai. Esperar aqui nao
    # esconde bug: reproduz o que um humano faria naturalmente.
    time.sleep(1.1)
    novo = c.post("/api/auth/login", json={"username": "tecnico", "password": "senha-inicial"})
    c.cookies.clear()
    assert novo.json()["role"] == "admin"
    assert c.get(
        "/api/usuarios", headers={"Authorization": f"Bearer {novo.json()['token']}"}
    ).status_code == 200


def test_nao_pode_rebaixar_o_ultimo_admin(equipe):
    """Deixaria a instalacao sem ninguem capaz de administrar."""
    c = equipe["client"]
    c.cookies.clear()
    r = c.patch("/api/usuarios/chefe/papel", json={"role": "staff"}, headers=equipe["admin"])
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ultimo_admin"


def test_nao_pode_desativar_o_ultimo_admin_nem_a_si_mesmo(equipe):
    c = equipe["client"]
    c.cookies.clear()
    r = c.patch("/api/usuarios/chefe/ativo", json={"ativo": False}, headers=equipe["admin"])
    assert r.status_code == 409
    assert r.json()["detail"]["code"] in ("autodesativacao", "ultimo_admin")


def test_desativar_corta_o_acesso_na_hora(equipe):
    c = equipe["client"]
    c.cookies.clear()
    assert c.get("/api/stats", headers=equipe["staff"]).status_code == 200

    r = c.patch("/api/usuarios/tecnico/ativo", json={"ativo": False}, headers=equipe["admin"])
    assert r.status_code == 200, r.text

    c.cookies.clear()
    assert c.get("/api/stats", headers=equipe["staff"]).status_code == 401, (
        "desativar sem revogar sessao seria cosmetico: o JWT ja emitido "
        "continuaria valendo por horas"
    )
    # E nao consegue entrar de novo.
    time.sleep(1.1)
    assert c.post(
        "/api/auth/login", json={"username": "tecnico", "password": "senha-inicial"}
    ).status_code == 403


def test_trocar_propria_senha_exige_a_atual(equipe):
    c = equipe["client"]
    c.cookies.clear()

    errada = c.post(
        "/api/usuarios/eu/senha",
        json={"senha_atual": "chute", "nova_senha": "nova-senha-longa"},
        headers=equipe["staff"],
    )
    assert errada.status_code == 401, (
        "sem exigir a senha atual, uma sessao esquecida aberta permitiria "
        "assumir a conta"
    )

    c.cookies.clear()
    ok = c.post(
        "/api/usuarios/eu/senha",
        json={"senha_atual": "senha-inicial", "nova_senha": "nova-senha-longa"},
        headers=equipe["staff"],
    )
    assert ok.status_code == 200, ok.text

    # A senha nova vale e a antiga nao.
    c.cookies.clear()
    time.sleep(1.1)  # janela de 1s do corte de revogacao
    assert c.post(
        "/api/auth/login", json={"username": "tecnico", "password": "nova-senha-longa"}
    ).status_code == 200
    c.cookies.clear()
    assert c.post(
        "/api/auth/login", json={"username": "tecnico", "password": "senha-inicial"}
    ).status_code == 401


def test_trocar_senha_encerra_as_sessoes(equipe):
    """Quem troca a senha geralmente suspeita que alguem tem acesso."""
    c = equipe["client"]
    c.cookies.clear()
    r = c.post(
        "/api/usuarios/eu/senha",
        json={"senha_atual": "senha-inicial", "nova_senha": "nova-senha-longa"},
        headers=equipe["staff"],
    )
    assert r.status_code == 200
    c.cookies.clear()
    assert c.get("/api/stats", headers=equipe["staff"]).status_code == 401


def test_reset_de_senha_por_admin(equipe):
    c = equipe["client"]
    c.cookies.clear()
    r = c.post(
        "/api/usuarios/tecnico/senha",
        json={"nova_senha": "definida-pelo-admin"},
        headers=equipe["admin"],
    )
    assert r.status_code == 200, r.text

    c.cookies.clear()
    assert c.get("/api/stats", headers=equipe["staff"]).status_code == 401
    c.cookies.clear()
    time.sleep(1.1)  # janela de 1s do corte de revogacao
    assert c.post(
        "/api/auth/login", json={"username": "tecnico", "password": "definida-pelo-admin"}
    ).status_code == 200
