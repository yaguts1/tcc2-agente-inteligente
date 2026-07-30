"""Testes de cenarios multi-paciente e persistencia idempotente."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from interface.dao import (
    contar_por_paciente,
    criar_esquema,
    inserir_alertas,
    inserir_grade,
)
from main import processar_alertas_multi

ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def _grade_runs(paciente_id: str, runs: Iterable[tuple[str, int]], inicio: str) -> pd.DataFrame:
    """Monta grade minuto a minuto a partir de blocos (postura, minutos)."""
    registros: list[tuple[str, str, str]] = []
    momento = pd.to_datetime(inicio)
    for postura, minutos in runs:
        idx = pd.date_range(start=momento, periods=minutos, freq="min")
        for ts in idx:
            registros.append((paciente_id, ts.strftime(ISO_FMT), postura))
        momento = idx[-1] + pd.Timedelta(minutes=1)
    return pd.DataFrame(registros, columns=["paciente_id", "timestamp", "postura"])


def test_processar_alertas_multi_mantem_grupos() -> None:
    grade_p1 = _grade_runs("P1", [("supino", 61)], "2025-01-01T00:00:00")
    grade_p2 = _grade_runs("P2", [("supino", 61)], "2025-01-01T00:00:00")
    df_grade = pd.concat([grade_p1, grade_p2], ignore_index=True)

    alertas = processar_alertas_multi(df_grade, "alto")

    pacientes_alertados = {alerta["paciente_id"] for alerta in alertas}
    assert pacientes_alertados == {"P1", "P2"}
    for paciente_id in ("P1", "P2"):
        assert any(alerta["paciente_id"] == paciente_id for alerta in alertas)


def test_dao_insercao_idempotente_por_paciente(tmp_path) -> None:
    db_path = tmp_path / "dados.db"
    criar_esquema(db_path)

    grade_p1 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01T00:00:00", periods=3, freq="min").strftime(ISO_FMT),
            "postura": ["supino", "supino", "prono"],
        }
    )
    grade_p2 = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01T02:00:00", periods=2, freq="min").strftime(ISO_FMT),
            "postura": ["supino", "lateral_direito"],
        }
    )

    assert inserir_grade(db_path, grade_p1, "P1") == len(grade_p1)
    assert inserir_grade(db_path, grade_p2, "P2") == len(grade_p2)
    assert inserir_grade(db_path, grade_p1, "P1") == 0
    assert inserir_grade(db_path, grade_p2, "P2") == 0

    contagem_grade = contar_por_paciente(db_path, "grade")
    assert contagem_grade == {"P1": 3, "P2": 2}

    alertas = [
        {
            "paciente_id": "P1",
            "inicio": "2025-01-01T01:00:00",
            "fim": None,
            "tipo": "imobilidade",
            "perfil": "alto",
            "janela_min": 60,
            "status": "aberto",
            "duracao_min": None,
        },
        {
            "paciente_id": "P2",
            "inicio": "2025-01-01T03:00:00",
            "fim": None,
            "tipo": "imobilidade",
            "perfil": "alto",
            "janela_min": 60,
            "status": "aberto",
            "duracao_min": None,
        },
    ]

    assert inserir_alertas(db_path, alertas) == len(alertas)
    assert inserir_alertas(db_path, alertas) == 0

    contagem_alertas = contar_por_paciente(db_path, "alertas")
    assert contagem_alertas == {"P1": 1, "P2": 1}
