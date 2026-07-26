"""Repository for ESP32 device operations (registration, events, assignment resolution)."""
from __future__ import annotations

import json

from interface.db_core import connect, utc_now_iso


def registrar_device(db_path: str, device_id: str, meta: dict | None = None) -> None:
    """Registra um device (ESP32) no banco, armazenando metadados opcionais."""
    if not device_id:
        raise ValueError("device_id deve ser informado.")
    meta_text = None if meta is None else json.dumps(meta, ensure_ascii=False)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO devices (device_id, meta) VALUES (?, ?)",
            (str(device_id), meta_text),
        )


def resolver_paciente_por_device_em(db_path: str, device_id: str, ts_ms: int) -> str | None:
    """Resolve qual paciente (se houver) estava associado ao device no instante `ts_ms`.

    Retorna o paciente_id ou None.
    """
    if not device_id:
        return None
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT paciente_id FROM device_assignments WHERE device_id = ? AND start_ms <= ? AND (end_ms IS NULL OR end_ms >= ?) ORDER BY start_ms DESC LIMIT 1",
            (device_id, int(ts_ms), int(ts_ms)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        pid = row["paciente_id"]
        return None if pid is None else str(pid)


def inserir_device_event(db_path: str, device_id: str, ts: str, ts_ms: int, payload: dict) -> int:
    """Armazena o payload bruto recebido de um device para posterior reconciliação.

    Retorna o id do registro inserido.
    """
    if not device_id:
        raise ValueError("device_id deve ser informado.")
    meta_text = json.dumps(payload, ensure_ascii=False)
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO device_events (device_id, ts, ts_ms, payload) VALUES (?, ?, ?, ?)",
            (device_id, ts, int(ts_ms), meta_text),
        )
        return int(cursor.lastrowid)


def contar_device_events(
    db_path: str, device_id: str | None = None, include_processed: bool = False
) -> int:
    """Quantos device_events existem com esses filtros, sem aplicar `limit`.

    Existe para o painel de orfaos poder dizer o TOTAL mesmo quando a listagem
    e cortada. `listar_device_events` limitado a N devolve N e nao ha como
    distinguir "existem N" de "existem muito mais": num painel cuja funcao e
    diagnosticar acumulo de eventos nao reconciliados, o numero parar de subir
    ao bater no teto e exatamente o contrario do que se precisa ver.
    """
    sql = "SELECT COUNT(*) FROM device_events"
    params: list = []
    where_clauses: list[str] = []
    if device_id:
        where_clauses.append("device_id = ?")
        params.append(device_id)
    if not include_processed:
        where_clauses.append("processed_at IS NULL")
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    with connect(db_path) as conn:
        return int(conn.execute(sql, tuple(params)).fetchone()[0])


def listar_device_events(db_path: str, device_id: str | None = None, limit: int = 100, include_processed: bool = False) -> list[dict]:
    """List device_events. By default only returns events where processed_at IS NULL.

    Set include_processed=True to return all events regardless of processed_at.
    """
    sql = "SELECT id, device_id, ts, ts_ms, payload, created_at, processed_at FROM device_events"
    params: list = []
    where_clauses: list[str] = []
    if device_id:
        where_clauses.append("device_id = ?")
        params.append(device_id)
    if not include_processed:
        where_clauses.append("processed_at IS NULL")
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    sql = f"{sql} ORDER BY ts_ms DESC LIMIT ?"
    params.append(int(limit))
    with connect(db_path) as conn:
        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()
    results: list[dict] = []
    for row in rows:
        try:
            payload_parsed = json.loads(row["payload"])
        except Exception:
            payload_parsed = None
        results.append({
            "id": row["id"],
            "device_id": row["device_id"],
            "ts": row["ts"],
            "ts_ms": int(row["ts_ms"]),
            "payload": payload_parsed,
            "created_at": row["created_at"],
            "processed_at": row["processed_at"],
        })
    return results


def listar_devices(db_path: str) -> list[dict]:
    with connect(db_path) as conn:
        cur = conn.execute("SELECT device_id, meta, created_at FROM devices ORDER BY created_at DESC")
        rows = cur.fetchall()
    results: list[dict] = []
    for row in rows:
        try:
            meta_parsed = None if row["meta"] is None else json.loads(row["meta"])
        except Exception:
            meta_parsed = None
        results.append({
            "device_id": row["device_id"],
            "meta": meta_parsed,
            "created_at": row["created_at"],
        })
    return results


def delete_device_event(db_path: str, event_id: int, processed_at: str | None = None) -> int:
    """Mark a device_events row as processed (set processed_at). Returns number of rows updated.

    This preserves the payload for auditability. If `processed_at` is None, current UTC timestamp is used.
    """
    if processed_at is None:
        processed_at = utc_now_iso()
    with connect(db_path) as conn:
        cur = conn.execute("UPDATE device_events SET processed_at = ? WHERE id = ? AND processed_at IS NULL", (processed_at, int(event_id)))
        return cur.rowcount


def resolver_paciente_por_cama_em(db_path: str, cama_id: str, ts_ms: int) -> str | None:
    """Quem ocupava a cama no instante `ts_ms`, segundo `paciente_cama_history`.

    A tabela de historico ja era mantida (start_ms/end_ms a cada troca de
    leito), mas nada a consultava: a reconciliacao usava a ficha ATUAL do
    paciente na cama, ou seja, o ocupante de agora, ignorando o instante da
    leitura.
    """
    if not cama_id:
        return None
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT paciente_id FROM paciente_cama_history"
            " WHERE cama_id = ? AND start_ms <= ? AND (end_ms IS NULL OR end_ms >= ?)"
            " ORDER BY start_ms DESC LIMIT 1",
            (str(cama_id), int(ts_ms), int(ts_ms)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        pid = row["paciente_id"]
        return None if pid is None else str(pid)
