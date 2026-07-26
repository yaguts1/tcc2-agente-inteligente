"""Repository for posture grade (grade) and raw event (eventos) bulk inserts."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from interface.db_core import connect, ensure_paciente, norm_iso, _ensure_grade_confianca_column
from interface.tempo import agora_utc_naive


def inserir_grade(
    db_path: str,
    df_grade: pd.DataFrame,
    paciente_id: str = "P1",
) -> int:
    """Insere amostras da grade simulada."""
    required = {"timestamp", "postura"}
    if not required.issubset(df_grade.columns):
        raise ValueError("df_grade precisa conter as colunas 'timestamp' e 'postura'.")

    timestamps = norm_iso(df_grade["timestamp"]).tolist()
    posturas = df_grade["postura"].astype(str).tolist()

    # Handle optional confianca
    if "confianca" in df_grade.columns:
        confiancas = df_grade["confianca"].fillna(1.0).tolist()
    else:
        confiancas = [1.0] * len(timestamps)

    registros = [
        (paciente_id, ts, postura, conf)
        for ts, postura, conf in zip(timestamps, posturas, confiancas)
        if ts is not None
    ]

    if not registros:
        return 0

    with connect(db_path) as conn:
        ensure_paciente(conn, paciente_id)
        _ensure_grade_confianca_column(conn)
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO grade (paciente_id, ts, postura, confianca) VALUES (?, ?, ?, ?)",
            registros,
        )
        return conn.total_changes - before


def inserir_eventos(
    db_path: str,
    df_eventos: pd.DataFrame,
    paciente_id: str = "P1",
) -> int:
    """Insere eventos simulados em lote."""
    required = {"inicio", "fim"}
    if not required.issubset(df_eventos.columns):
        raise ValueError("df_eventos precisa conter as colunas 'inicio' e 'fim'.")

    tipo_col = "tipo" if "tipo" in df_eventos.columns else "origem"
    if tipo_col not in df_eventos.columns:
        raise ValueError("df_eventos precisa conter a coluna 'tipo' ou 'origem'.")

    inicios = norm_iso(df_eventos["inicio"]).tolist()
    fins = norm_iso(df_eventos["fim"]).tolist()
    tipos = df_eventos[tipo_col].astype(str).tolist()

    registros = [
        (paciente_id, inicio, fim, tipo)
        for inicio, fim, tipo in zip(inicios, fins, tipos)
        if inicio is not None
    ]

    if not registros:
        return 0

    with connect(db_path) as conn:
        ensure_paciente(conn, paciente_id)
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO eventos (paciente_id, inicio, fim, tipo) VALUES (?, ?, ?, ?)",
            registros,
        )
        return conn.total_changes - before


def selecionar_grade_janela(db_path: str, horas: int | None = 24) -> list[dict]:
    """Busca eventos de grade (postura) dentro de uma janela de tempo."""
    if horas is None:
        with connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT paciente_id, ts, postura, confianca FROM grade ORDER BY ts ASC"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # `ts` no banco é UTC naive — datetime.now() local deslocaria a janela
    # pelo offset do fuso (ver interface/tempo.py).
    agora = agora_utc_naive()
    limite_inferior = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")
    limite_superior = (agora + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")

    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, ts, postura, confianca FROM grade WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
            (limite_inferior, limite_superior),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]
