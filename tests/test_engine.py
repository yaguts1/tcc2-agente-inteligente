"""Tests for the alert engine."""

from __future__ import annotations

from typing import Iterable, List, Tuple

import pandas as pd
import pytest

from modulo_alerta.engine import processar_alertas

ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def _grade_from_runs(runs: Iterable[Tuple[str, int]], start: str = "2025-01-01T00:00:00") -> pd.DataFrame:
    """Builds a minute-by-minute grade from (posture, size) runs."""
    runs_list: List[Tuple[str, int]] = list(runs)
    periods = sum(count for _, count in runs_list)
    timestamps = pd.date_range(start=start, periods=periods, freq="min")
    posturas: List[str] = []
    for postura, count in runs_list:
        posturas.extend([postura] * count)
    return pd.DataFrame({"timestamp": timestamps, "postura": posturas})


def test_abertura_perfil_alto() -> None:
    df_grade = _grade_from_runs([( "supino", 61)])

    df_norm, alertas = processar_alertas(df_grade, "alto", "P1")

    assert all(ts.endswith("00") for ts in df_norm["timestamp"])  # ISO minute precision
    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta["status"] == "aberto"
    assert alerta["inicio"] == "2025-01-01T01:00:00"
    assert alerta["janela_min"] == 60
    assert alerta["paciente_id"] == "P1"


def test_cooldown_nao_reabre_alerta_curto() -> None:
    runs = [
        ("supino", 61),        # abre alerta
        ("lateral_direito", 2),  # movimento curto (<5min) nao fecha
        ("supino", 20),        # novo bloco dentro do cooldown
    ]
    df_grade = _grade_from_runs(runs)

    _, alertas = processar_alertas(df_grade, "alto", "P1")

    assert len(alertas) == 1
    assert alertas[0]["status"] == "aberto"
    assert alertas[0].get("fim") in (None, "NaT")


def test_histerese_fecha_alerta() -> None:
    runs = [
        ("supino", 61),           # abre alerta
        ("lateral_esquerdo", 6),  # 5 min de histerese => fecha
    ]
    df_grade = _grade_from_runs(runs)

    _, alertas = processar_alertas(df_grade, "alto", "P1")

    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta["status"] == "fechado"
    assert alerta["inicio"] == "2025-01-01T01:00:00"
    assert alerta["fim"] == "2025-01-01T01:06:00"
    assert alerta["duracao_min"] == pytest.approx(6.0)
