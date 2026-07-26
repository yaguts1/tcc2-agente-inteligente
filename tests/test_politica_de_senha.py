"""A politica de senha vale nos TRES caminhos que definem senha.

O numero 8 ja existia — em dois lugares, e nao no que importa.
`/usuarios/eu/senha` e `/usuarios/{u}/senha` exigiam 8 caracteres, mas
`/auth/register` aceitava qualquer senha nao vazia: dava para CRIAR a conta
com "a" e so entao ser impedido de TROCAR para "a". Como o primeiro usuario da
instalacao vira admin, era a conta administrativa que nascia sem exigencia
nenhuma.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.api_shared import SENHA_MIN_LEN

CURTA = "a" * (SENHA_MIN_LEN - 1)
VALIDA = "a" * SENHA_MIN_LEN


@pytest_asyncio.fixture()
async def anonimo(app_isolado):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture()
async def admin(app_isolado, cabecalho_auth):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=cabecalho_auth(username="chefe", role="admin"),
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_cadastro_recusa_senha_curta(anonimo):
    """O caminho que CRIA a conta — e a primeira delas e a de admin."""
    resp = await anonimo.post(
        "/api/auth/register", json={"username": "novo", "password": CURTA}
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "senha_fraca"


@pytest.mark.asyncio
async def test_cadastro_aceita_senha_na_politica(anonimo):
    resp = await anonimo.post(
        "/api/auth/register", json={"username": "novo", "password": VALIDA}
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_reset_por_admin_recusa_senha_curta(admin, app_isolado):
    from interface.repositories.users import UserRepository

    UserRepository(app_isolado.db_path).create("alvo", "hash-qualquer")

    resp = await admin.post("/api/usuarios/alvo/senha", json={"nova_senha": CURTA})

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "senha_fraca"


@pytest.mark.asyncio
async def test_troca_propria_recusa_senha_curta(admin):
    resp = await admin.post(
        "/api/usuarios/eu/senha",
        json={"senha_atual": "qualquer", "nova_senha": CURTA},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "senha_fraca"


@pytest.mark.asyncio
async def test_senha_fraca_e_recusada_antes_de_conferir_a_atual(admin):
    """A politica e checada antes da senha atual, e o codigo diz qual foi o erro.

    Se a ordem fosse a inversa, quem digitasse a senha atual errada E uma nova
    curta receberia "senha atual incorreta" e corrigiria a coisa errada.
    """
    resp = await admin.post(
        "/api/usuarios/eu/senha",
        json={"senha_atual": "com-certeza-errada", "nova_senha": CURTA},
    )

    assert resp.json()["detail"]["code"] == "senha_fraca"


@pytest.mark.asyncio
async def test_mensagem_diz_o_que_corrigir(anonimo):
    """400 com texto legivel, e nao o 422 de validacao do pydantic.

    O corpo do 422 e uma lista de erros de campo; o formulario de cadastro
    exibiria "Erro 422", que nao diz a ninguem o que fazer.
    """
    resp = await anonimo.post(
        "/api/auth/register", json={"username": "novo", "password": CURTA}
    )

    assert str(SENHA_MIN_LEN) in resp.json()["detail"]["message"]
