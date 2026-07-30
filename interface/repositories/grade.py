"""Repository for posture grade (grade) and raw event (eventos) bulk inserts."""
from __future__ import annotations

from datetime import timedelta

import sqlite3

import pandas as pd
import structlog

from interface.db_core import (
    conexao_ou_propria,
    connect,
    ensure_paciente,
    norm_iso,
    _ensure_grade_confianca_column,
)
from interface.tempo import agora_utc_naive

logger = structlog.get_logger(__name__)


def _para_ts_ms(serie: pd.Series) -> list[int | None]:
    """Timestamps em milissegundos inteiros, sem o arredondamento de `norm_iso`.

    `norm_iso` existe para o texto de `ts`, que e de segundo cheio em todo o
    banco. Aqui a precisao e o ponto: e o que impede duas amostras do mesmo
    segundo de colidirem na chave primaria.
    """
    convertidos = pd.to_datetime(serie, errors="coerce", utc=False)
    if getattr(convertidos.dtype, "tz", None) is not None:
        convertidos = convertidos.dt.tz_convert(None)
    return [
        None if pd.isna(valor) else int(valor.timestamp() * 1000)
        for valor in convertidos
    ]


def inserir_grade(
    db_path: str,
    df_grade: pd.DataFrame,
    paciente_id: str = "P1",
    conn: "sqlite3.Connection | None" = None,
) -> int:
    """Insere amostras da grade simulada."""
    required = {"timestamp", "postura"}
    if not required.issubset(df_grade.columns):
        raise ValueError("df_grade precisa conter as colunas 'timestamp' e 'postura'.")

    timestamps = norm_iso(df_grade["timestamp"]).tolist()
    # `ts_ms` guarda a precisao que `ts` perde no `.dt.floor("s")` de `norm_iso`.
    # E ele, nao `ts`, que compoe a chave primaria — ver migrations/0008: com a
    # chave em segundos, duas amostras do mesmo segundo colidiam e a segunda era
    # descartada em silencio pelo `INSERT OR IGNORE`.
    ts_ms_series = _para_ts_ms(df_grade["timestamp"])
    posturas = df_grade["postura"].astype(str).tolist()

    # Handle optional confianca
    if "confianca" in df_grade.columns:
        confiancas = df_grade["confianca"].fillna(1.0).tolist()
    else:
        confiancas = [1.0] * len(timestamps)

    # `pressao_pico` era DECLARADO no schema, atravessava o exportador JSONL e
    # nunca era gravado: um dado que o firmware ja envia e que o sistema jogava
    # fora a cada amostra. E o unico sinal capaz de distinguir "o rotulo de
    # postura mudou" de "a carga sobre o sacro foi aliviada".
    if "pressao_pico" in df_grade.columns:
        pressoes = [None if pd.isna(v) else float(v) for v in df_grade["pressao_pico"]]
    else:
        pressoes = [None] * len(timestamps)

    registros = [
        (paciente_id, ts, ts_ms, postura, conf, pressao)
        for ts, ts_ms, postura, conf, pressao in zip(
            timestamps, ts_ms_series, posturas, confiancas, pressoes
        )
        if ts is not None and ts_ms is not None
    ]

    if not registros:
        return 0

    with conexao_ou_propria(db_path, conn) as cx:
        ensure_paciente(cx, paciente_id)
        _ensure_grade_confianca_column(cx, db_path)
        before = cx.total_changes
        cx.executemany(
            "INSERT OR IGNORE INTO grade"
            " (paciente_id, ts, ts_ms, postura, confianca, pressao_pico)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            registros,
        )
        inseridos = cx.total_changes - before

    # `OR IGNORE` continua sendo o que queremos — reenvio do dispositivo e
    # reingestao de evento orfao dependem dele para serem idempotentes. O que
    # nao pode continuar e o descarte ser INVISIVEL: era assim que o teto de uma
    # amostra por segundo se escondia, e e assim que qualquer teto futuro se
    # esconderia. A partir daqui, sumir amostra deixa rastro.
    descartadas = len(registros) - inseridos
    if descartadas > 0:
        logger.info(
            "grade_amostras_ignoradas",
            paciente_id=paciente_id,
            enviadas=len(registros),
            gravadas=inseridos,
            ignoradas=descartadas,
            motivo="chave (paciente_id, ts_ms) ja existente",
        )

    return inseridos


def inserir_eventos(
    db_path: str,
    df_eventos: pd.DataFrame,
    paciente_id: str = "P1",
    conn: "sqlite3.Connection | None" = None,
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

    with conexao_ou_propria(db_path, conn) as cx:
        ensure_paciente(cx, paciente_id)
        before = cx.total_changes
        cx.executemany(
            "INSERT OR IGNORE INTO eventos (paciente_id, inicio, fim, tipo) VALUES (?, ?, ?, ?)",
            registros,
        )
        return cx.total_changes - before


def selecionar_grade_janela(db_path: str, horas: int | None = 24) -> list[dict]:
    """Busca eventos de grade (postura) dentro de uma janela de tempo."""
    if horas is None:
        with connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT paciente_id, ts, postura, confianca FROM grade ORDER BY ts ASC, ts_ms ASC"
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
            # `ts_ms` desempata: com varias amostras no mesmo segundo, `ORDER BY
            # ts` sozinho deixa a ordem entre elas a criterio do SQLite — e essa
            # sequencia alimenta o replay do decisor, que depende de ordem.
            "SELECT paciente_id, ts, postura, confianca FROM grade"
            " WHERE ts >= ? AND ts <= ? ORDER BY ts ASC, ts_ms ASC",
            (limite_inferior, limite_superior),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]
