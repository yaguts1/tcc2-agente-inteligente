# -*- coding: utf-8 -*-
"""Gerador de massa para UI

Este script usa as funções em dados_simulados/gerador.py para gerar
grades e eventos e salvá-los em CSV dentro de dados_simulados/gerados_ui/.

Uso (exemplo):
    python dados_simulados/generate_ui.py --pacientes 1 --horas 36 --passo 2 --seed 42

Produz arquivos com nomes no formato:
  PAC-0001_grade_36h_2m_seed42_YYYYmmdd_HHMMSS.csv

"""
from __future__ import annotations
import argparse
from datetime import datetime
import os
from pathlib import Path

import pandas as pd

from dados_simulados.gerador import gerar_sessao_simulada, gerar_eventos_sessao, gerar_sessao_multi


OUT_DIR = Path(__file__).resolve().parent / "gerados_ui"


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def write_grade_csv(df: pd.DataFrame, paciente_id: str, horas: int, passo: int, seed: int) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{paciente_id}_grade_{horas}h_{passo}m_seed{seed}_{ts}.csv"
    path = OUT_DIR / fname
    df.to_csv(path, index=False)
    return path


def write_eventos_csv(df: pd.DataFrame, paciente_id: str, horas: int, seed: int) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{paciente_id}_eventos_{horas}h_seed{seed}_{ts}.csv"
    path = OUT_DIR / fname
    # salvar eventos brutos (com inicio/fim se disponíveis)
    df.to_csv(path, index=False)
    return path


def generate_single(paciente_id: str, horas: int, passo: int, seed: int) -> list[Path]:
    now = datetime.now()
    # gerar grade regular
    df_grade = gerar_sessao_simulada(duracao_horas=horas, seed=seed, passo_min=passo, inicio=None)
    # adiciona coluna paciente_id
    df_grade.insert(0, "paciente_id", paciente_id)

    grade_path = write_grade_csv(df_grade, paciente_id, horas, passo, seed)

    # gerar eventos brutos (intervalos)
    df_eventos = gerar_eventos_sessao(duracao_horas=horas, seed=seed, inicio=None)
    df_eventos.insert(0, "paciente_id", paciente_id)
    eventos_path = write_eventos_csv(df_eventos, paciente_id, horas, seed)

    return [grade_path, eventos_path]


def generate_multi(n: int, horas: int, passo: int, seed: int) -> list[Path]:
    paths: list[Path] = []
    df_grade_all, df_eventos_all = gerar_sessao_multi(pacientes=n, horas=horas, passo_min=passo, seed=seed)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    grade_fname = f"multi_grade_{n}p_{horas}h_{passo}m_seed{seed}_{ts}.csv"
    eventos_fname = f"multi_eventos_{n}p_{horas}h_seed{seed}_{ts}.csv"
    grade_path = OUT_DIR / grade_fname
    eventos_path = OUT_DIR / eventos_fname
    df_grade_all.to_csv(grade_path, index=False)
    df_eventos_all.to_csv(eventos_path, index=False)
    paths.extend([grade_path, eventos_path])
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gerador de massa para UI (dados_simulados)")
    parser.add_argument("--pacientes", "-p", type=int, default=1, help="Número de pacientes (1 para single)")
    parser.add_argument("--horas", "-H", type=int, default=36, help="Duração em horas")
    parser.add_argument("--passo", "-m", type=int, default=2, help="Passo da grade em minutos")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Seed aleatória")
    parser.add_argument("--paciente-id", type=str, default="PAC-0001", help="ID do paciente (para --pacientes 1)")

    args = parser.parse_args(argv)

    ensure_out_dir()

    if args.pacientes == 1:
        print(f"Gerando 1 paciente: {args.paciente_id}, {args.horas}h, passo {args.passo}m, seed {args.seed}")
        paths = generate_single(args.paciente_id, args.horas, args.passo, args.seed)
    else:
        print(f"Gerando {args.pacientes} pacientes: {args.pacientes}, {args.horas}h, passo {args.passo}m, seed {args.seed}")
        paths = generate_multi(args.pacientes, args.horas, args.passo, args.seed)

    for p in paths:
        print("Escreveu:", p)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
