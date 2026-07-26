"""Autorizacao por papel (role).

O JWT ja carregava `role` e o /auth/me o devolvia, mas NADA no projeto
verificava: a autorizacao era binaria — autenticado ou nao. Na pratica,
qualquer conta recem-criada podia importar alertas em massa, apagar todos os
backups e injetar dados sinteticos no banco de producao.

Pior: `UserRepository.create` nunca gravava a coluna `role`, entao TODO usuario
ficava com o default "staff" do schema. Se os endpoints passassem a exigir
admin sem corrigir isso, eles se tornariam inalcancaveis.

Regra adotada: o PRIMEIRO usuario da instalacao vira admin (alguem precisa
poder administrar); os demais, staff.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def contas(app_isolado):
    """Cria o admin (bootstrap) e um staff, devolvendo client e tokens."""
    client = TestClient(app_isolado.app)

    r_admin = client.post("/api/auth/register", json={"username": "dona", "password": "senha-de-teste"})
    assert r_admin.status_code == 201, r_admin.text
    token_admin = r_admin.json()["token"]

    r_staff = client.post(
        "/api/auth/register",
        json={"username": "enfermeira", "password": "senha-de-teste"},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert r_staff.status_code == 201, r_staff.text

    client.cookies.clear()
    return {
        "client": client,
        "admin": {"Authorization": f"Bearer {token_admin}"},
        "staff": {"Authorization": f"Bearer {r_staff.json()['token']}"},
        "papel_admin": r_admin.json()["role"],
        "papel_staff": r_staff.json()["role"],
    }


def test_primeiro_usuario_e_admin_os_demais_staff(contas):
    assert contas["papel_admin"] == "admin"
    assert contas["papel_staff"] == "staff"


@pytest.mark.parametrize(
    "metodo,rota,corpo",
    [
        ("GET", "/api/admin/backup/list", None),
        ("POST", "/api/admin/backup/create", None),
        ("POST", "/api/admin/import_alerts", []),
        ("POST", "/api/pacientes/PAC-1/simular", {"duracao_horas": 1}),
    ],
)
def test_staff_nao_acessa_endpoints_administrativos(contas, metodo, rota, corpo):
    client = contas["client"]
    client.cookies.clear()
    resp = client.request(metodo, rota, headers=contas["staff"], json=corpo)
    assert resp.status_code == 403, (
        f"{metodo} {rota} deveria ser 403 para staff, veio {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize(
    "metodo,rota,corpo",
    [
        ("GET", "/api/admin/backup/list", None),
        ("POST", "/api/admin/import_alerts", []),
        ("POST", "/api/pacientes/PAC-1/simular", {"duracao_horas": 1}),
    ],
)
def test_admin_passa_pela_autorizacao(contas, metodo, rota, corpo):
    """Admin nao pode ser barrado por PAPEL.

    O status pode ser 400/404 (validacao ou recurso inexistente adiante) — o
    que importa e nao ser 401/403.
    """
    client = contas["client"]
    client.cookies.clear()
    resp = client.request(metodo, rota, headers=contas["admin"], json=corpo)
    assert resp.status_code not in (401, 403), (
        f"admin barrado em {metodo} {rota}: {resp.status_code} {resp.text}"
    )


@pytest.mark.parametrize("rota", ["/api/pacientes", "/api/stats", "/api/frontend/alerts"])
def test_staff_mantem_acesso_clinico(contas, rota):
    """Contrapartida: restringir o administrativo nao pode tolher o uso clinico
    — é para isso que a conta staff existe."""
    client = contas["client"]
    client.cookies.clear()
    resp = client.get(rota, headers=contas["staff"])
    assert resp.status_code == 200, f"staff perdeu acesso a {rota}: {resp.text}"


def test_papel_vem_do_token_e_nao_do_cliente(contas):
    """Enviar um papel via header/corpo nao pode conceder privilegio: a fonte é
    o JWT assinado."""
    client = contas["client"]
    client.cookies.clear()
    resp = client.get(
        "/api/admin/backup/list",
        headers={**contas["staff"], "X-Role": "admin", "Role": "admin"},
    )
    assert resp.status_code == 403
