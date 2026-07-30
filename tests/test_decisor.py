from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

import configuracao
from nucleo.decisor import EstadoDecisor, processar_alertas_incremental, processar_alertas_lote


def _montar_grade(posturas: list[str], inicio: datetime | None = None, passo_min: int = 5) -> pd.DataFrame:
    inicio = inicio or datetime(2024, 1, 1, 0, 0)
    registros = []
    for indice, postura in enumerate(posturas):
        registros.append(
            {
                "timestamp": inicio + timedelta(minutes=passo_min * indice),
                "postura": postura,
            }
        )
    return pd.DataFrame(registros)


def test_processar_alertas_lote_abre_alerta() -> None:
    grade = _montar_grade(["supino"] * 22)
    alertas = processar_alertas_lote(grade, "medio", "PAC-0001")
    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta["paciente_id"] == "PAC-0001"
    assert alerta["status"] == "aberto"
    assert alerta["inicio"] == "2024-01-01T01:30:00"
    assert alerta["janela_min"] == 90


def test_processar_alertas_lote_fecha_alerta() -> None:
    grade = _montar_grade(["supino"] * 21 + ["lateral_direito"] * 4)
    alertas = processar_alertas_lote(grade, "medio", "PAC-0002")
    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta["status"] == "fechado"
    assert alerta["fim"] == "2024-01-01T01:50:00"
    assert pytest.approx(alerta["duracao_min"], abs=1e-6) == 20.0


def test_processar_alertas_incremental_ordem_monotona() -> None:
    estado = EstadoDecisor.criar("medio", "PAC-0003")
    estado, _ = processar_alertas_incremental(
        estado,
        {"timestamp": datetime(2024, 1, 1, 0, 0), "postura": "supino"},
    )
    with pytest.raises(ValueError):
        processar_alertas_incremental(
            estado,
            {"timestamp": datetime(2023, 12, 31, 23, 59), "postura": "supino"},
        )


def test_processar_alertas_incremental_equivalente_lote() -> None:
    grade = _montar_grade(["supino"] * 21 + ["lateral_direito"] * 4)
    estado = EstadoDecisor.criar("medio", "PAC-0004")
    acumulado: dict[tuple[str, str], dict] = {}
    ordem: list[tuple[str, str]] = []
    for linha in grade.to_dict("records"):
        estado, alertas = processar_alertas_incremental(estado, linha)
        for alerta in alertas:
            chave = (alerta["paciente_id"], alerta["inicio"])
            if chave not in acumulado:
                ordem.append(chave)
            acumulado[chave] = alerta
    incremental_result = [acumulado[chave] for chave in ordem]
    lote_result = processar_alertas_lote(grade, "medio", "PAC-0004")
    assert incremental_result == lote_result


def test_configuracao_respeita_variavel_de_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock _load_env_file to ignore .env file content
    monkeypatch.setattr(configuracao, "_load_env_file", dict)

    monkeypatch.setattr(configuracao, "_ENV_CACHE", None, raising=False)
    monkeypatch.setenv("MODE", "stream")
    cfg_stream = configuracao.carregar_configuracao()
    assert cfg_stream.modo_operacao == "stream"

    monkeypatch.delenv("MODE", raising=False)
    monkeypatch.setattr(configuracao, "_ENV_CACHE", None, raising=False)
    cfg_padrao = configuracao.carregar_configuracao()
    assert cfg_padrao.modo_operacao == "batch"
