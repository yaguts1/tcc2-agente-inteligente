"""Unidades (alas/setores) e quais delas cada usuario enxerga.

O escopo por unidade e uma regra de SEGURANCA, nao de apresentacao: e o que
impede toda enfermeira do predio de ler o dado clinico de todo paciente. Por
isso a decisao de "quais unidades este usuario ve" mora num lugar so, aqui, e
nao espalhada em cada consulta.

Convencao central, usada por todo consumidor:

    None  -> sem restricao (admin ve o hospital inteiro)
    set() -> conjunto vazio; o usuario nao ve NADA

`set()` vazio nao pode virar "ve tudo" por acidente. E a diferenca entre um
staff recem-criado sem unidade nenhuma ver uma tela vazia (correto, e a tela
avisa) e ele ver o hospital inteiro (vazamento). Em Python `if not unidades:`
trata os dois casos igual — por isso as funcoes abaixo sempre comparam com
`is None` explicitamente.
"""
from __future__ import annotations

import sqlite3

import structlog

from interface.db_core import connect

logger = structlog.get_logger(__name__)

# Criada por migrations/0010 para receber os dados anteriores ao conceito de
# unidade. Nomeada porque varios pontos precisam de um destino padrao quando o
# chamador nao informa unidade nenhuma.
UNIDADE_PADRAO = 1


class UnidadeInvalida(ValueError):
    """Unidade inexistente ou inativa."""


def listar_unidades(db_path: str, incluir_inativas: bool = False) -> list[dict]:
    sql = "SELECT id, nome, descricao, ativo FROM unidades"
    if not incluir_inativas:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY nome"
    with connect(db_path) as conn:
        return [dict(linha) for linha in conn.execute(sql)]


def criar_unidade(db_path: str, nome: str, descricao: str | None = None) -> dict:
    nome_limpo = str(nome or "").strip()
    if not nome_limpo:
        raise ValueError("Nome da unidade nao pode ser vazio.")
    with connect(db_path) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO unidades (nome, descricao) VALUES (?, ?)",
                (nome_limpo, descricao),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Ja existe uma unidade chamada '{nome_limpo}'.") from exc
        return {"id": int(cur.lastrowid), "nome": nome_limpo, "descricao": descricao, "ativo": 1}


def assert_unidade_valida(conn: sqlite3.Connection, unidade_id: int | None) -> None:
    if unidade_id is None:
        return
    linha = conn.execute(
        "SELECT ativo FROM unidades WHERE id = ?", (int(unidade_id),)
    ).fetchone()
    if linha is None:
        raise UnidadeInvalida(f"Unidade {unidade_id} nao existe.")
    if not linha["ativo"]:
        raise UnidadeInvalida(f"Unidade {unidade_id} esta inativa.")


def unidades_do_usuario(db_path: str, username: str, papel: str | None = None) -> set[int] | None:
    """Unidades que este usuario enxerga. `None` = todas.

    Admin ve o hospital inteiro: e quem administra unidades, cria contas e
    responde pela instalacao — restringi-lo criaria o estado em que ninguem
    consegue consertar um vinculo errado.

    Para os demais, o conjunto vem de `usuario_unidade`. Um staff sem vinculo
    nenhum recebe `set()` e nao ve nada — deny by default. E deliberado: o
    contrario (sem vinculo = ve tudo) transformaria esquecer de vincular num
    vazamento silencioso, que e o pior default possivel para dado de saude.
    """
    if (papel or "").strip().lower() == "admin":
        return None
    with connect(db_path) as conn:
        linhas = conn.execute(
            "SELECT unidade_id FROM usuario_unidade WHERE username = ?", (username,)
        ).fetchall()
    return {int(linha["unidade_id"]) for linha in linhas}


def definir_unidades_do_usuario(db_path: str, username: str, unidades: list[int]) -> list[int]:
    with connect(db_path) as conn:
        if conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone() is None:
            raise LookupError(f"Usuario {username} nao encontrado.")
        for unidade_id in unidades:
            assert_unidade_valida(conn, unidade_id)
        conn.execute("DELETE FROM usuario_unidade WHERE username = ?", (username,))
        conn.executemany(
            "INSERT INTO usuario_unidade (username, unidade_id) VALUES (?, ?)",
            [(username, int(u)) for u in unidades],
        )
    logger.info("unidades_do_usuario_definidas", usuario=username, unidades=unidades)
    return [int(u) for u in unidades]


def filtro_sql(unidades: set[int] | None, coluna: str = "f.unidade_id") -> tuple[str, list]:
    """Fragmento SQL e parametros para restringir uma consulta as unidades.

    Devolve `("", [])` quando nao ha restricao (admin), e uma condicao sempre
    falsa quando o conjunto e vazio.

    O ramo do conjunto vazio existe porque `IN ()` e erro de sintaxe no SQLite, e
    a tentacao natural — pular o filtro quando nao ha unidades — devolveria o
    hospital inteiro exatamente para quem nao pode ver nada.
    """
    if unidades is None:
        return "", []
    if not unidades:
        return " AND 1 = 0", []
    marcadores = ",".join("?" for _ in unidades)
    return f" AND {coluna} IN ({marcadores})", [int(u) for u in sorted(unidades)]
