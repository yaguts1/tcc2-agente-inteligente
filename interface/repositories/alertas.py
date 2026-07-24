"""Repository for alert (alertas) operations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pandas as pd

from interface.db_core import connect, ensure_paciente, norm_iso
from interface.repositories.timeline import inserir_timeline_event
from interface.tempo import agora_utc_naive

_VALID_TABLES = {"grade", "eventos", "alertas"}


def inserir_alertas(db_path: str, alertas: List[dict]) -> int:
    """Insere ou atualiza alertas calculados pelo motor."""
    if not alertas:
        return 0

    required = {"paciente_id", "inicio", "tipo", "perfil", "janela_min", "status"}
    for alerta in alertas:
        if not required.issubset(alerta):
            raise ValueError(
                "Alertas devem conter pelo menos paciente_id, inicio, tipo, perfil, janela_min e status."
            )

    inicio_series = norm_iso(pd.Series([alerta.get("inicio") for alerta in alertas], dtype="object"))
    fim_series = norm_iso(pd.Series([alerta.get("fim") for alerta in alertas], dtype="object"))

    registros = []
    pacientes: set[str] = set()
    for idx, alerta in enumerate(alertas):
        paciente_id = str(alerta["paciente_id"])
        inicio_val = inicio_series.iat[idx]
        if inicio_val is None:
            raise ValueError("Alertas precisam de 'inicio' valido para persistencia.")
        fim_val = fim_series.iat[idx]
        duracao = alerta.get("duracao_min")
        duracao_val = float(duracao) if duracao is not None else None
        registros.append(
            (
                paciente_id,
                inicio_val,
                fim_val,
                str(alerta.get("tipo", "")),
                str(alerta.get("perfil", "")),
                int(alerta.get("janela_min", 0)),
                str(alerta.get("status", "")),
                duracao_val,
            )
        )
        pacientes.add(paciente_id)

    if not registros:
        return 0

    with connect(db_path) as conn:
        for paciente in pacientes:
            ensure_paciente(conn, paciente)
        before = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO alertas
            (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros,
        )
        # number of DB changes caused by alert inserts only
        delta_alerts = conn.total_changes - before
        # For each alerta we persisted, add a timeline event so historical navigation
        # can reflect when alerts were generated. We insert an event with tipo 'alert_open'
        # using the inicio timestamp from the alerta payload and an epoch ms for easier queries.
        try:
            for idx, alerta in enumerate(alertas):
                paciente_id = str(alerta["paciente_id"]) if isinstance(alerta, dict) else registros[idx][0]
                inicio_val = inicio_series.iat[idx]
                status_val = str(alerta.get("status", "")) if isinstance(alerta, dict) else registros[idx][6]
                if inicio_val is None:
                    continue
                # only log opening events for alerts that are 'aberto' or were inserted now
                if status_val.lower() != "aberto":
                    continue
                ts_iso = inicio_val
                try:
                    ts_ms = int(pd.to_datetime(ts_iso).timestamp() * 1000)
                except Exception:
                    ts_ms = None
                if ts_ms is None:
                    continue
                conn.execute(
                    "INSERT INTO timeline_events (paciente_id, ts, ts_ms, tipo, descricao, meta) VALUES (?, ?, ?, ?, ?, ?)",
                    (paciente_id, ts_iso, ts_ms, "alert_open", None, None),
                )
        except Exception:
            # Do not fail alert insertion for timeline logging errors
            pass
        return int(delta_alerts)


def contar_por_paciente(db_path: str, tabela: str) -> Dict[str, int]:
    """Retorna a contagem de registros agrupada por paciente."""
    if tabela not in _VALID_TABLES:
        raise ValueError(f"Tabela desconhecida: {tabela}")

    with connect(db_path) as conn:
        cursor = conn.execute(
            f"SELECT paciente_id, COUNT(*) as total FROM {tabela} GROUP BY paciente_id"
        )
        rows = cursor.fetchall()
    return {str(row["paciente_id"]): int(row["total"]) for row in rows}


def listar_alertas_abertos(db_path: str) -> List[dict]:
    """Retorna alertas em aberto."""
    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min"
            " FROM alertas WHERE status = ?",
            ("aberto",),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def selecionar_alertas_janela(db_path: str, horas: int | None = 24) -> list[dict]:
    """Busca alertas (qualquer status) dentro de uma janela de tempo.

    Args:
        db_path: Caminho do banco de dados
        horas: Janela de tempo em horas (se None, traz todos)
              Busca alertas de (agora - horas) até (agora + horas)

    Returns:
        Lista de dicts com dados dos alertas ordenados por inicio ASC
    """
    if horas is None:
        # Sem filtro de tempo - retorna todos
        with connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
                "FROM alertas ORDER BY inicio ASC"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # Com filtro de tempo - busca passado e futuro próximo.
    # `inicio` no banco é UTC naive, então o "agora" da janela também precisa
    # ser UTC (datetime.now() local deslocaria a janela pelo offset do fuso).
    agora = agora_utc_naive()
    limite_inferior = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")
    limite_superior = (agora + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")

    with connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
            "FROM alertas WHERE inicio >= ? AND inicio <= ? ORDER BY inicio ASC",
            (limite_inferior, limite_superior),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def listar_pacientes(db_path: str, horas: int | None = 24) -> list[str]:
    limite = None
    if horas is not None:
        agora = agora_utc_naive()  # `inicio` no banco é UTC naive
        limite = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")
    with connect(db_path) as conn:
        if limite is None:
            cur = conn.execute("SELECT DISTINCT paciente_id FROM alertas ORDER BY paciente_id")
        else:
            cur = conn.execute(
                "SELECT DISTINCT paciente_id FROM alertas WHERE inicio >= ? ORDER BY paciente_id",
                (limite,),
            )
        rows = cur.fetchall()
    return [str(row[0]) for row in rows]


def alterar_status_alerta(
    db_path: str,
    paciente_id: str,
    inicio: str,
    status_destino: str,
    definir_fim: bool = False,
    now_dt: datetime | None = None,
) -> None:
    """Atualiza o status de um alerta e registra evento de timeline quando aplicavel.

    - status_destino: 'aberto'|'reconhecido'|'fechado'
    - if definir_fim is True, sets fim and duracao_min based on now_dt or current time.
    """
    if not paciente_id or not inicio:
        raise ValueError("paciente_id e inicio precisam ser informados")
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT paciente_id FROM alertas WHERE paciente_id = ? AND inicio = ?",
            (paciente_id, inicio),
        )
        if cur.fetchone() is None:
            raise LookupError("Alerta nao encontrado.")

        params = {"paciente_id": paciente_id, "inicio": inicio}
        if definir_fim:
            # `inicio` é UTC naive; o "agora" (fim) e a duração precisam do
            # mesmo referencial (senão datetime.now() local erraria a duração
            # pelo offset do fuso). Callers podem passar now_dt (relógio virtual).
            base_now = (now_dt or agora_utc_naive()).replace(microsecond=0)
            ini_dt = datetime.fromisoformat(inicio[:19])
            fim_iso = base_now.strftime("%Y-%m-%dT%H:%M:%S")
            duracao_min = round((base_now - ini_dt).total_seconds() / 60.0, 2)
            conn.execute(
                """
                UPDATE alertas
                SET status = :status, fim = :fim, duracao_min = :duracao_min
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {
                    "status": status_destino,
                    "paciente_id": paciente_id,
                    "inicio": inicio,
                    "fim": fim_iso,
                    "duracao_min": duracao_min,
                },
            )
            # timeline log for alert close
            try:
                ts_iso = fim_iso
                # ts_ms: base_now é UTC naive → tratar como UTC no epoch (idem
                # aos demais ts_ms, calculados via pandas que assume UTC).
                ts_ms = int(base_now.replace(tzinfo=timezone.utc).timestamp() * 1000)
                inserir_timeline_event(db_path, paciente_id, ts_iso, ts_ms, "alert_close", descricao=None, meta={"inicio": inicio})
            except Exception:
                pass
        else:
            conn.execute(
                """
                UPDATE alertas
                SET status = :status
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {"status": status_destino, **params},
            )
            # timeline log for acknowledgement
            try:
                if str(status_destino).lower() == "reconhecido":
                    base_now = agora_utc_naive()
                    ts_iso = base_now.strftime("%Y-%m-%dT%H:%M:%S")
                    ts_ms = int(base_now.replace(tzinfo=timezone.utc).timestamp() * 1000)
                    inserir_timeline_event(db_path, paciente_id, ts_iso, ts_ms, "alert_ack", descricao=None, meta={"inicio": inicio})
            except Exception:
                pass
        conn.commit()
