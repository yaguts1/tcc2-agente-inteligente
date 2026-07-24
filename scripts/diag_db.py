#!/usr/bin/env python3
"""SQLite diagnostics for the pressure-ulcer agent database.

Usage:
    python scripts/diag_db.py --db dados.db

Parameters:
    --db: path to the SQLite file (default: dados.db). Use absolute paths when
          running outside the project root.

The script prints:
  - total rows in grade, eventos and alertas tables;
  - alert counts grouped by patient and status;
  - latest grade timestamp per patient;
  - alerts with start older than 24 hours (candidates for cleanup);
  - duplicated primary keys (entries ignored by idempotent inserts), listing up
    to three of the most recent duplicates per table.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple


@dataclass
class Section:
    title: str
    headers: Sequence[str]
    rows: Sequence[Sequence[object]]
    note: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite diagnostics for the agent database.")
    parser.add_argument("--db", default="dados.db", help="Path to the SQLite file (default: dados.db)")
    return parser.parse_args()


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def fetch_single_value(conn: sqlite3.Connection, sql: str, params: Tuple[object, ...] = ()) -> int | None:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return None if row is None else row[0]


def format_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    if not rows:
        return "(sem dados)"

    str_rows: List[List[str]] = [["" if value is None else str(value) for value in row] for row in rows]
    col_widths = [len(str(header)) for header in headers]

    for row in str_rows:
        for idx, value in enumerate(row):
            if len(value) > col_widths[idx]:
                col_widths[idx] = len(value)

    header_line = " | ".join(f"{header:<{col_widths[idx]}}" for idx, header in enumerate(headers))
    separator = "-+-".join("-" * width for width in col_widths)
    body_lines = [
        " | ".join(f"{value:<{col_widths[idx]}}" for idx, value in enumerate(row))
        for row in str_rows
    ]
    return "\n".join([header_line, separator, *body_lines])


def build_counts_section(conn: sqlite3.Connection) -> Section:
    tables = ("grade", "eventos", "alertas")
    rows = []
    for table in tables:
        if table_exists(conn, table):
            total = fetch_single_value(conn, f"SELECT COUNT(*) FROM {table}")
            rows.append((table, total or 0))
        else:
            rows.append((f"{table} (missing)", "-"))
    return Section("Totais por tabela", ("Tabela", "Linhas"), rows)


def build_alerts_by_status(conn: sqlite3.Connection) -> Section:
    if not table_exists(conn, "alertas"):
        return Section("Alertas por paciente/status", ("Paciente", "Status", "Total"), [])

    sql = (
        "SELECT paciente_id, status, COUNT(*) AS total "
        "FROM alertas GROUP BY paciente_id, status ORDER BY paciente_id, status"
    )
    rows = conn.execute(sql).fetchall()
    return Section("Alertas por paciente/status", ("Paciente", "Status", "Total"), rows)


def build_grade_latest(conn: sqlite3.Connection) -> Section:
    if not table_exists(conn, "grade"):
        return Section("Ultimos timestamps por paciente (grade)", ("Paciente", "Ultimo timestamp"), [])

    sql = "SELECT paciente_id, MAX(ts) AS ultimo FROM grade GROUP BY paciente_id ORDER BY paciente_id"
    rows = conn.execute(sql).fetchall()
    return Section("Ultimos timestamps por paciente (grade)", ("Paciente", "Ultimo timestamp"), rows)


def build_old_alerts(conn: sqlite3.Connection) -> Section:
    if not table_exists(conn, "alertas"):
        return Section("Alertas com inicio > 24h", ("Paciente", "Inicio", "Status"), [])

    sql = (
        "SELECT paciente_id, inicio, status "
        "FROM alertas "
        "WHERE inicio IS NOT NULL "
        "AND datetime(replace(inicio, 'T', ' ')) < datetime('now','-24 hours') "
        "ORDER BY inicio ASC"
    )
    rows = conn.execute(sql).fetchall()
    return Section(
        "Alertas com inicio > 24h",
        ("Paciente", "Inicio", "Status"),
        rows,
        note="Mostra alertas cujo inicio ocorreu ha mais de 24 horas.",
    )


def duplicate_summary(
    conn: sqlite3.Connection,
    table: str,
    pk_columns: Sequence[str],
    order_column: str,
    limit: int = 3,
) -> Tuple[int, List[Tuple[object, ...]]]:
    if not table_exists(conn, table):
        return 0, []

    group_cols = ", ".join(pk_columns)
    duplicates_sql = (
        f"SELECT {group_cols}, COUNT(*) AS repeticoes "
        f"FROM {table} "
        f"GROUP BY {group_cols} "
        "HAVING repeticoes > 1 "
        f"ORDER BY MAX({order_column}) DESC "
        f"LIMIT {limit}"
    )
    rows = conn.execute(duplicates_sql).fetchall()

    total_sql = (
        f"SELECT COALESCE(SUM(cnt - 1), 0) FROM ("
        f"SELECT COUNT(*) AS cnt FROM {table} GROUP BY {group_cols} HAVING cnt > 1"
        ")"
    )
    total = fetch_single_value(conn, total_sql) or 0
    return total, rows


def build_duplicates_section(conn: sqlite3.Connection) -> Section:
    items = [
        ("grade", ("paciente_id", "ts"), "ts"),
        ("eventos", ("paciente_id", "inicio"), "inicio"),
        ("alertas", ("paciente_id", "inicio"), "inicio"),
    ]
    rows: List[Tuple[str, int]] = []
    details: List[List[str]] = []

    for table, pk_cols, order_col in items:
        total, dup_rows = duplicate_summary(conn, table, pk_cols, order_col)
        rows.append((table, total))
        for dup in dup_rows:
            *keys, repeticoes = dup
            key_repr = ", ".join(str(key) for key in keys)
            details.append([table, key_repr, repeticoes])

    note_lines: List[str] = []
    if details:
        detail_headers = ("Tabela", "Chave (PK)", "Repeticoes")
        note_lines.append("Duplicidades detectadas (ate 3 mais recentes por tabela):")
        note_lines.append(format_table(detail_headers, details))
    else:
        note_lines.append("Nenhuma duplicidade encontrada nas chaves primarias monitoradas.")

    section_note = "\n".join(note_lines)
    return Section("Entradas ignoradas por idempotencia", ("Tabela", "Duplicidades"), rows, note=section_note)


def render_section(section: Section) -> None:
    print(f"\n== {section.title} ==")
    print(format_table(section.headers, section.rows))
    if section.note:
        print(section.note)


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        raise SystemExit(f"Arquivo de banco nao encontrado: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        sections = [
            build_counts_section(conn),
            build_alerts_by_status(conn),
            build_grade_latest(conn),
            build_old_alerts(conn),
            build_duplicates_section(conn),
        ]

    for section in sections:
        render_section(section)


if __name__ == "__main__":
    main()
