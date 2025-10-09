"""Motor de decisao de alertas para imobilidade em leito."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

_PROFILE_CONFIG = MappingProxyType({
    "baixo": {"janela_minutos": 120, "cooldown_minutos": 10, "histerese_minutos": 5},
    "medio": {"janela_minutos": 90, "cooldown_minutos": 10, "histerese_minutos": 5},
    "alto": {"janela_minutos": 60, "cooldown_minutos": 10, "histerese_minutos": 5},
})


def _to_iso(value: datetime | pd.Timestamp) -> str:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    value = value.replace(microsecond=0)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def _abrir(inicio: datetime, perfil: str, janela_min: int, paciente_id: str) -> Dict[str, Any]:
    return {
        "paciente_id": paciente_id,
        "inicio": _to_iso(inicio),
        "tipo": "imobilidade",
        "perfil": perfil,
        "janela_min": janela_min,
        "status": "aberto",
    }


def _fechar(alerta: Dict[str, Any], fim: datetime, inicio: datetime) -> Dict[str, Any]:
    alerta["fim"] = _to_iso(fim)
    alerta["status"] = "fechado"
    alerta["duracao_min"] = round((fim - inicio).total_seconds() / 60.0, 2)
    return alerta


def processar_alertas(
    df_grade: pd.DataFrame,
    perfil: str,
    paciente_id: str,
    min_conf: float = 0.0,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Processa a serie de posturas e calcula alertas de imobilidade.

    Args:
        df_grade: Grade temporal de posturas com colunas ``timestamp`` (str) e ``postura`` (str).
        perfil: Classificacao do paciente ("baixo", "medio", ou "alto").
        paciente_id: Identificador do paciente associado aos dados.
        min_conf: Limite minimo de confianca (reservado para uso futuro).

    Returns:
        Tupla ``(df_grade_norm, alertas)`` com timestamps normalizados e alertas gerados.

    Raises:
        ValueError: Quando o perfil eh invalido ou os dados nao possuem colunas esperadas.
    """
    _ = min_conf  # reservado para evolucoes futuras

    if "timestamp" not in df_grade.columns or "postura" not in df_grade.columns:
        raise ValueError("df_grade precisa conter as colunas 'timestamp' e 'postura'.")

    config = _PROFILE_CONFIG.get(perfil)
    if config is None:
        raise ValueError(f"Perfil desconhecido: {perfil}")

    janela_td = timedelta(minutes=config["janela_minutos"])
    cooldown_td = timedelta(minutes=config["cooldown_minutos"])
    histerese_min = float(config["histerese_minutos"])

    df_norm = df_grade.copy(deep=True)
    ts_series = pd.to_datetime(df_norm["timestamp"], errors="raise", utc=True)
    ts_series = ts_series.dt.tz_convert(None)

    if not ts_series.is_monotonic_increasing:
        raise ValueError("Timestamps devem estar em ordem crescente.")

    timestamps = [ts.to_pydatetime() for ts in ts_series]
    posturas = df_norm["postura"].astype(str).tolist()

    df_norm["timestamp"] = ts_series.dt.strftime("%Y-%m-%dT%H:%M:%S")

    if not timestamps:
        return df_norm, []

    alertas: List[Dict[str, Any]] = []
    alerta_atual: Optional[Dict[str, Any]] = None
    alerta_inicio_dt: Optional[datetime] = None
    baseline_postura: Optional[str] = None
    movimento_inicio: Optional[datetime] = None
    cooldown_until = datetime.min

    run_postura = posturas[0]
    run_inicio = timestamps[0]

    for idx in range(1, len(timestamps)):
        ts_atual = timestamps[idx]
        postura_atual = posturas[idx]

        if postura_atual != run_postura:
            run_postura = postura_atual
            run_inicio = ts_atual

        if alerta_atual is not None and baseline_postura is not None:
            # Controla movimento sustentado fora da baseline ate atingir a histerese.
            if postura_atual != baseline_postura:
                if movimento_inicio is None:
                    movimento_inicio = ts_atual
                mov_seq_min = max((ts_atual - movimento_inicio).total_seconds() / 60.0, 0.0)
            else:
                movimento_inicio = None
                mov_seq_min = 0.0

            if movimento_inicio is not None and mov_seq_min >= histerese_min:
                fim_alerta = ts_atual
                if alerta_inicio_dt is None:
                    raise RuntimeError("Estado interno invalido: alerta sem inicio associado.")
                alerta_atual = _fechar(alerta_atual, fim_alerta, alerta_inicio_dt)
                cooldown_until = ts_atual + cooldown_td  # aplica cooldown apos fechamento
                alerta_atual = None
                alerta_inicio_dt = None
                baseline_postura = None
                movimento_inicio = None
                continue

        if alerta_atual is None:
            detection_time = run_inicio + janela_td
            inicio_alerta = max(detection_time, cooldown_until)
            if inicio_alerta <= ts_atual:
                baseline_postura = run_postura
                alerta_inicio_dt = inicio_alerta
                alerta_atual = _abrir(inicio_alerta, perfil, config["janela_minutos"], paciente_id)
                alertas.append(alerta_atual)
                movimento_inicio = None

    return df_norm, alertas
