"""Runner de migrations simples para SQLite: tabela schema_version +
scripts .sql numerados nesta pasta, aplicados em ordem dentro de uma
transacao. Sem dependencia externa (nao usa Alembic/SQLAlchemy) porque o
projeto acessa o banco via sqlite3 cru.

Uso:
    python -m migrations upgrade --db-path dados.db
    python -m migrations upgrade  # usa UPP_DB_PATH ou "dados.db"

Ou programaticamente:
    from migrations.runner import upgrade
    upgrade(db_path)
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parent
_FILENAME_RE = re.compile(r"^(\d+)_.*\.sql$")


def _ensure_parent_dir(db_path: str) -> Path:
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(db_path: str) -> sqlite3.Connection:
    path = _ensure_parent_dir(db_path)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _listar_migrations() -> list[tuple[int, Path]]:
    """Lista os arquivos NNNN_nome.sql desta pasta, ordenados por numero."""
    migrations = []
    for arquivo in _MIGRATIONS_DIR.glob("*.sql"):
        match = _FILENAME_RE.match(arquivo.name)
        if not match:
            continue
        migrations.append((int(match.group(1)), arquivo))
    migrations.sort(key=lambda item: item[0])
    return migrations


def _versao_atual(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def upgrade(db_path: str) -> int:
    """Aplica todas as migrations pendentes. Retorna a versao final do schema."""
    conn = _connect(db_path)
    try:
        versao_atual = _versao_atual(conn)
        pendentes = [(v, arq) for v, arq in _listar_migrations() if v > versao_atual]

        for versao, arquivo in pendentes:
            sql = arquivo.read_text(encoding="utf-8")
            with conn:  # transacao: commit no fim do bloco, rollback se falhar
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (versao,)
                )
            versao_atual = versao

        return versao_atual
    finally:
        conn.close()


def versao_schema(db_path: str) -> int:
    """Retorna a versao de schema atualmente aplicada, sem alterar nada."""
    conn = _connect(db_path)
    try:
        return _versao_atual(conn)
    finally:
        conn.close()
