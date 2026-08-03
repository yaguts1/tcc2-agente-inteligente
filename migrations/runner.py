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

# Mesmo valor de interface.db_core.BUSY_TIMEOUT_MS, repetido de proposito: este
# modulo e deliberadamente independente do resto do app (ver docstring acima) e
# importar interface.db_core criaria um ciclo — db_core.criar_esquema chama
# este runner.
BUSY_TIMEOUT_MS = 5000

_MIGRATIONS_DIR = Path(__file__).resolve().parent
_FILENAME_RE = re.compile(r"^(\d+)_.*\.sql$")


def _ensure_parent_dir(db_path: str) -> Path:
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(db_path: str) -> sqlite3.Connection:
    path = _ensure_parent_dir(db_path)
    # busy_timeout: migrations rodam no startup, quando o reconciler e o
    # scheduler de backup ja podem estar tocando o banco. Sem isso a primeira
    # colisao aborta a migration.
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    # Autocommit: o controle de transacao passa a ser EXPLICITO, dentro do
    # script (ver `_aplicar`). Com o modo legado, o driver abre transacao
    # sozinho para DML e nao para DDL — duas regras diferentes no mesmo runner,
    # e foi essa ambiguidade que escondeu a migration nao-atomica.
    conn.isolation_level = None
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
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


def _aplicar(conn: sqlite3.Connection, versao: int, sql: str) -> None:
    """Aplica UMA migration inteira, ou nenhuma parte dela.

    O BEGIN/COMMIT vai DENTRO do script, e nao em volta da chamada. A versao
    anterior fazia:

        with conn:                    # "transacao: rollback se falhar"
            conn.executescript(sql)

    e o comentario estava errado. `executescript` emite um COMMIT implicito
    ANTES de rodar e, nas palavras da documentacao, "nenhum outro controle de
    transacao e realizado; qualquer controle de transacao deve ser adicionado ao
    script". O `with conn:` nao envolvia nada: cada statement commitava sozinho.

    O custo era uma migration com backfill (a `0010_unidades.sql` tem 15
    statements) falhando no meio: os primeiros ficavam aplicados, o
    `schema_version` nao avancava, e a subida seguinte reaplicava do inicio para
    morrer em "duplicate column name" — para sempre, sem caminho de volta.

    O `INSERT` da versao entra no MESMO script de proposito: schema e versao
    precisam avancar juntos, senao um crash entre os dois recria o mesmo impasse.
    A interpolacao de `versao` e segura por construcao — vem de
    `_FILENAME_RE`, que so casa digitos.
    """
    try:
        conn.executescript(
            "BEGIN;\n"
            f"{sql}\n"
            f"INSERT INTO schema_version (version) VALUES ({int(versao)});\n"
            "COMMIT;"
        )
    except Exception:
        # A transacao fica ABERTA quando o script morre antes do COMMIT: sem o
        # rollback explicito, o proximo `executescript` a commitaria junto com o
        # trabalho seguinte — transformando uma falha limpa em corrupcao.
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass  # nao havia transacao aberta; a falha original e que importa
        raise


def upgrade(db_path: str) -> int:
    """Aplica todas as migrations pendentes. Retorna a versao final do schema."""
    conn = _connect(db_path)
    try:
        versao_atual = _versao_atual(conn)
        pendentes = [(v, arq) for v, arq in _listar_migrations() if v > versao_atual]

        for versao, arquivo in pendentes:
            _aplicar(conn, versao, arquivo.read_text(encoding="utf-8"))
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
