"""Repository for timeline event operations."""
from __future__ import annotations

import json

from interface.db_core import connect, ensure_paciente


def inserir_timeline_event(
    db_path: str,
    paciente_id: str,
    ts: str,
    ts_ms: int,
    tipo: str,
    descricao: str | None = None,
    meta: dict | None = None,
) -> int:
    """Insere um evento na timeline e retorna o id do registro inserido."""
    if not ts or ts_ms is None:
        raise ValueError("ts e ts_ms devem ser informados para inserir um evento de timeline.")
    meta_text = None if meta is None else json.dumps(meta, ensure_ascii=False)
    with connect(db_path) as conn:
        # paciente_id may be None or empty for generic events; only ensure paciente when provided
        if paciente_id:
            ensure_paciente(conn, paciente_id)
        cursor = conn.execute(
            "INSERT INTO timeline_events (paciente_id, ts, ts_ms, tipo, descricao, meta) VALUES (?, ?, ?, ?, ?, ?)",
            (paciente_id, ts, int(ts_ms), tipo, descricao, meta_text),
        )
        return int(cursor.lastrowid)


def ultimo_evento_por_paciente(
    db_path: str,
    paciente_ids: list[str],
    tipos: list[str],
) -> dict[str, str]:
    """Timestamp do evento mais recente de cada paciente, entre os `tipos` dados.

    Uma unica query para todos os pacientes. Existe para eliminar o N+1 de
    `listar_alertas_frontend`, que chamava `selecionar_timeline(limit=50)` uma
    vez POR ALERTA so para descobrir o ultimo reposicionamento.

    Retorna {paciente_id: ts}. Pacientes sem evento ficam de fora.
    """
    if not paciente_ids or not tipos:
        return {}

    marcadores_ids = ",".join("?" for _ in paciente_ids)
    marcadores_tipos = ",".join("?" for _ in tipos)
    # `ts` acompanha o MAX(ts_ms) do grupo: no SQLite, uma coluna "solta" junto
    # de MAX() vem da linha que produziu esse maximo (bare columns).
    sql = (
        "SELECT paciente_id, ts, MAX(ts_ms) AS ts_ms FROM timeline_events "
        f"WHERE paciente_id IN ({marcadores_ids}) AND tipo IN ({marcadores_tipos}) "
        "GROUP BY paciente_id"
    )
    with connect(db_path) as conn:
        linhas = conn.execute(sql, (*paciente_ids, *tipos)).fetchall()
    return {str(linha["paciente_id"]): linha["ts"] for linha in linhas if linha["ts"] is not None}


def selecionar_timeline(
    db_path: str,
    paciente_id: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1000,
    tipo: str | None = None,
) -> list[dict]:
    """Seleciona eventos da timeline aplicando filtros opcionais. Retorna lista de dicts.

    Ordena por `ts_ms` ascendente.
    """
    sql = "SELECT id, paciente_id, ts, ts_ms, tipo, descricao, meta, created_at FROM timeline_events"
    params: list = []
    where_clauses: list[str] = []
    if paciente_id:
        where_clauses.append("paciente_id = ?")
        params.append(paciente_id)
    if tipo:
        where_clauses.append("tipo = ?")
        params.append(tipo)
    if start_ms is not None:
        where_clauses.append("ts_ms >= ?")
        params.append(int(start_ms))
    if end_ms is not None:
        where_clauses.append("ts_ms <= ?")
        params.append(int(end_ms))
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    sql = f"{sql} ORDER BY ts_ms DESC LIMIT ?"
    params.append(int(limit))
    with connect(db_path) as conn:
        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()
    results: list[dict] = []
    for row in rows:
        meta_val = row["meta"]
        try:
            meta_parsed = None if meta_val is None else json.loads(meta_val)
        except Exception:
            meta_parsed = None
        results.append(
            {
                "id": row["id"],
                "paciente_id": row["paciente_id"],
                "ts": row["ts"],
                "ts_ms": int(row["ts_ms"]),
                "tipo": row["tipo"],
                "descricao": row["descricao"],
                "meta": meta_parsed,
                "created_at": row["created_at"],
            }
        )
    return results
