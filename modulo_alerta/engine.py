"""Motor de decisao de alertas para imobilidade em leito."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from nucleo.decisor import processar_alertas_lote


def processar_alertas(
    df_grade: pd.DataFrame,
    perfil: str,
    paciente_id: str,
    min_conf: float = 0.0,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Processa a serie de posturas e calcula alertas de imobilidade."""
    _ = min_conf  # reservado para evolucoes futuras

    if "timestamp" not in df_grade.columns or "postura" not in df_grade.columns:
        raise ValueError("df_grade precisa conter as colunas 'timestamp' e 'postura'.")

    df_norm = df_grade.copy(deep=True)
    ts_series = pd.to_datetime(df_norm["timestamp"], errors="raise", utc=True).dt.tz_convert(None)

    if not ts_series.is_monotonic_increasing:
        raise ValueError("Timestamps devem estar em ordem crescente.")

    df_norm["timestamp"] = ts_series.dt.strftime("%Y-%m-%dT%H:%M:%S")

    timestamps_py = ts_series.dt.to_pydatetime()
    dados_lote = pd.DataFrame({"timestamp": timestamps_py, "postura": df_norm["postura"].astype(str)})

    alertas = processar_alertas_lote(dados_lote, perfil, paciente_id)

    return df_norm, alertas
