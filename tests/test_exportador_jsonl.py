from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest

from ferramentas.exportador_jsonl import ExportacaoInvalidaError, exportar_grade_para_jsonl, main


def _ler_jsonl(path: Path) -> list[dict]:
    return [json.loads(linha) for linha in path.read_text(encoding="utf-8").splitlines()]


def test_exportar_grade_para_jsonl_normaliza_campos(tmp_path: Path) -> None:
    destino = tmp_path / "eventos.jsonl"
    dados = [
        {
            "device_id": "esp01",
            "paciente_id": "P1",
            "cama_id": "C01",
            "postura": "supino",
            "confianca": "0.95",
            "amostra_ms": "300000",
            "timestamp": "2024-01-01T00:00:00Z",
        },
        {
            "device_id": "esp01",
            "paciente_id": "P1",
            "cama_id": "C01",
            "postura": "lateral_direito",
            "confianca": 0.87,
            "amostra_ms": 300000,
            "ts_utc": datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc),
            "pressao_pico": "12.5",
        },
    ]

    exportar_grade_para_jsonl(destino, dados)

    linhas = _ler_jsonl(destino)
    assert len(linhas) == 2
    primeiro = linhas[0]
    assert primeiro["ts_utc"] == "2024-01-01T00:00:00"
    assert pytest.approx(primeiro["confianca"], abs=1e-6) == 0.95
    segundo = linhas[1]
    assert segundo["pressao_pico"] == pytest.approx(12.5)


def test_exportar_grade_para_jsonl_streaming(tmp_path: Path) -> None:
    destino = tmp_path / "grande.jsonl"
    quantidade = 10_000

    def gerador() -> Generator[dict, None, None]:
        for idx in range(quantidade):
            yield {
                "device_id": "esp01",
                "paciente_id": f"P{idx%5}",
                "cama_id": f"C{idx%3}",
                "postura": "supino",
                "confianca": 0.9,
                "amostra_ms": 300000,
                "ts_utc": f"2024-01-01T00:{idx%60:02d}:00",
            }

    exportar_grade_para_jsonl(destino, gerador())
    linhas = destino.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == quantidade


def test_main_csv_para_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entrada = tmp_path / "grade.csv"
    saida = tmp_path / "eventos.jsonl"
    entrada.write_text(
        "paciente_id,timestamp,postura\n"
        "P1,2024-01-01T00:00:00,supino\n"
        "P1,2024-01-01T00:05:00,lateral_direito\n",
        encoding="utf-8",
    )

    argv = [
        "--entrada",
        str(entrada),
        "--saida",
        str(saida),
        "--device-id",
        "esp01",
        "--cama-id",
        "C01",
        "--confianca",
        "0.9",
        "--amostra-ms",
        "300000",
    ]

    assert main(argv) == 0
    linhas = _ler_jsonl(saida)
    assert [linha["postura"] for linha in linhas] == ["supino", "lateral_direito"]


def test_exportar_grade_para_jsonl_falha_sem_campos(tmp_path: Path) -> None:
    destino = tmp_path / "falha.jsonl"
    dados = [
        {
            "paciente_id": "P1",
            "cama_id": "C01",
            "postura": "supino",
            "confianca": 0.9,
            "amostra_ms": 300000,
            "ts_utc": "2024-01-01T00:00:00",
        }
    ]
    with pytest.raises(ExportacaoInvalidaError):
        exportar_grade_para_jsonl(destino, dados)
