"""Revogacao de sessao e contas desativaveis.

O JWT e autocontido: uma vez emitido vale ate expirar. Sem registro do lado do
servidor nao havia como encerrar sessao — o logout so apagava os cookies e o
token seguia valido pelas 8h. Na pratica nao existia forma de tirar o acesso de
ninguem: nem ao desligar um funcionario, nem depois de uma senha vazar, nem ao
sair do sistema num computador compartilhado.
"""

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from interface.repositories.sessoes import (
    limpar_tokens_expirados,
    revogar_sessoes_do_usuario,
)


@pytest.fixture
def conta(app_isolado):
    client = TestClient(app_isolado.app)
    resp = client.post("/api/auth/register", json={"username": "ana", "password": "pw"})
    assert resp.status_code == 201, resp.text
    client.cookies.clear()
    return {
        "client": client,
        "db": app_isolado.db_path,
        "auth": {"Authorization": f"Bearer {resp.json()['token']}"},
    }


def _logar(conta) -> dict:
    conta["client"].cookies.clear()
    r = conta["client"].post("/api/auth/login", json={"username": "ana", "password": "pw"})
    assert r.status_code == 200, r.text
    conta["client"].cookies.clear()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_logout_invalida_o_token_de_verdade(conta):
    c, h = conta["client"], conta["auth"]
    assert c.get("/api/stats", headers=h).status_code == 200

    c.post("/api/auth/logout", headers=h)
    c.cookies.clear()

    assert c.get("/api/stats", headers=h).status_code == 401, (
        "o token continuou valendo apos o logout — quem tivesse copiado o token "
        "(ou usasse o header Authorization) seguiria autenticado pelas horas restantes"
    )


def test_logout_nao_derruba_as_outras_sessoes(conta):
    """Sair num dispositivo nao pode desconectar os demais."""
    c = conta["client"]
    outra = _logar(conta)

    c.post("/api/auth/logout", headers=conta["auth"])
    c.cookies.clear()

    assert c.get("/api/stats", headers=outra).status_code == 200


def test_revogar_todas_as_sessoes(conta):
    """Troca de senha / saida forcada: invalida tudo que ja foi emitido."""
    c = conta["client"]
    sessao = _logar(conta)
    assert c.get("/api/stats", headers=sessao).status_code == 200

    # O corte tem resolucao de 1s (timestamp ISO), entao aguarda para garantir
    # que o token fique estritamente ANTES dele.
    time.sleep(1.1)
    revogar_sessoes_do_usuario(conta["db"], "ana")

    assert c.get("/api/stats", headers=sessao).status_code == 401


def test_conta_desativada_perde_acesso_imediato(conta):
    c = conta["client"]
    sessao = _logar(conta)
    assert c.get("/api/stats", headers=sessao).status_code == 200

    with sqlite3.connect(conta["db"]) as cx:
        cx.execute("UPDATE users SET ativo = 0 WHERE username = 'ana'")

    assert c.get("/api/stats", headers=sessao).status_code == 401, (
        "token de conta desativada continuou valendo"
    )


def test_conta_desativada_nao_consegue_logar(conta):
    """Senao revogar as sessoes de um desligado seria inutil: bastaria logar."""
    c = conta["client"]
    with sqlite3.connect(conta["db"]) as cx:
        cx.execute("UPDATE users SET ativo = 0 WHERE username = 'ana'")

    r = c.post("/api/auth/login", json={"username": "ana", "password": "pw"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "conta_desativada"


def test_usuario_removido_perde_a_sessao(conta):
    """Apagar a conta tem de encerrar o acesso.

    A validacao aceitava qualquer `sub` sem linha em `users`, para acomodar o
    login de fallback por variavel de ambiente. O efeito colateral era que um
    usuario REMOVIDO seguia autenticado ate o token expirar — o oposto do que
    remover a conta significa.
    """
    c = conta["client"]
    sessao = _logar(conta)
    assert c.get("/api/stats", headers=sessao).status_code == 200

    with sqlite3.connect(conta["db"]) as cx:
        cx.execute("DELETE FROM users WHERE username = 'ana'")

    c.cookies.clear()
    assert c.get("/api/stats", headers=sessao).status_code == 401


def test_limpeza_remove_apenas_revogacoes_expiradas(conta):
    """A denylist nao pode crescer para sempre: depois que o token expira por
    conta propria, a linha nao serve mais para nada."""
    with sqlite3.connect(conta["db"]) as cx:
        cx.execute(
            "INSERT INTO tokens_revogados (jti, expira_em) VALUES (?, ?)",
            ("ja-expirou", "2020-01-01T00:00:00"),
        )
        cx.execute(
            "INSERT INTO tokens_revogados (jti, expira_em) VALUES (?, ?)",
            ("ainda-vale", "2999-01-01T00:00:00"),
        )

    removidos = limpar_tokens_expirados(conta["db"])
    assert removidos == 1

    with sqlite3.connect(conta["db"]) as cx:
        restantes = {r[0] for r in cx.execute("SELECT jti FROM tokens_revogados")}
    assert restantes == {"ainda-vale"}
