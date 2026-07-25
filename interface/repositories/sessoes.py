"""Revogacao de sessoes (tokens JWT).

O JWT e autocontido: uma vez emitido, vale ate expirar. Sem um registro do lado
do servidor nao ha como encerrar sessao — o logout so apagava os cookies e o
token seguia valido pelas 8h. Na pratica nao existia forma de tirar o acesso de
alguem, nem ao desligar um funcionario, nem depois de uma senha vazar.

Tres mecanismos, cada um para um caso (ver migrations/0002_sessoes_e_contas.sql):

- `revogar_token(jti)` .......... encerra UMA sessao (logout num dispositivo);
- `revogar_sessoes_do_usuario()`  corte por data: invalida TODAS as sessoes
                                  anteriores ao instante gravado;
- coluna `users.ativo` .......... desliga a conta inteira.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from interface.db_core import connect, utc_now_iso

logger = structlog.get_logger(__name__)


def revogar_token(db_path: str, jti: str, expira_em: datetime, username: str | None = None) -> None:
    """Marca um token especifico como revogado ate a sua propria expiracao."""
    if not jti:
        return
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tokens_revogados (jti, username, expira_em) VALUES (?, ?, ?)",
            (jti, username, expira_em.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")),
        )


def token_esta_revogado(db_path: str, jti: str) -> bool:
    if not jti:
        return False
    with connect(db_path) as conn:
        linha = conn.execute(
            "SELECT 1 FROM tokens_revogados WHERE jti = ?", (jti,)
        ).fetchone()
    return linha is not None


def revogar_sessoes_do_usuario(db_path: str, username: str) -> None:
    """Invalida todas as sessoes ja emitidas para o usuario.

    Grava o instante do corte; tokens com `iat` anterior deixam de ser aceitos.
    Mais barato e mais confiavel do que tentar enumerar os tokens em circulacao
    — nao sabemos quais existem.
    """
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET tokens_validos_apos = ? WHERE username = ?",
            (utc_now_iso(), username),
        )
    logger.info("sessoes_revogadas", usuario=username)


def limpar_tokens_expirados(db_path: str) -> int:
    """Remove revogacoes de tokens que ja expiraram por conta propria.

    Depois da expiracao a linha nao serve para nada: o token seria recusado de
    qualquer forma. Sem esta limpeza a tabela cresceria indefinidamente.
    """
    agora = utc_now_iso()
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM tokens_revogados WHERE expira_em < ?", (agora,))
        return int(cur.rowcount or 0)


def estado_da_conta(db_path: str, username: str) -> Optional[dict]:
    """Devolve {ativo, tokens_validos_apos} ou None se o usuario nao existe."""
    with connect(db_path) as conn:
        linha = conn.execute(
            "SELECT ativo, tokens_validos_apos FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if linha is None:
        return None
    return {
        "ativo": bool(linha["ativo"]),
        "tokens_validos_apos": linha["tokens_validos_apos"],
    }
