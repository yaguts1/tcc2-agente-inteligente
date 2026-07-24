"""Generate simulated sessions and register them in the DB so alerts are created.

This script uses the project's internal ingestion logic (same code path as
the API) so generated samples produce alerts exactly as real devices would.

Usage (from repo root, with venv activated):
    python scripts\generate_alerts.py --patients 3 --hours 6 --seed 42

It will create simple patient records (ids P1..PN) if they don't exist, then
generate grade samples and register them via the same _registrar_evento code
used by the /api/eventos endpoint.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path
from datetime import datetime
from typing import Any

import pandas as pd

from dados_simulados.gerador import gerar_sessao_multi

from interface.dao import criar_paciente
from interface.api import _normalizar_payload, _registrar_evento
from interface.api import DB_PATH


def ensure_patient(pid: str) -> None:
    # create a minimal patient record; criar_paciente returns the ficha
    try:
        criar_paciente(DB_PATH, nome=f"Paciente {pid}", perfil="medio", cama_id=pid, observacoes="Gerado para testes")
    except Exception:
        # ignore if exists
        pass


def main(patients: int, hours: int, passo_min: int, seed: int) -> None:
    print(f"Generating sessions for {patients} patients, {hours}h each, seed={seed}")
    # ensure patients exist
    for i in range(patients):
        pid = f"P{i+1}"
        ensure_patient(pid)

    grade_df, eventos_df = gerar_sessao_multi(pacientes=patients, horas=hours, passo_min=passo_min, seed=seed)

    # grade_df has columns: paciente_id, timestamp, postura
    print("Registering samples and triggering processing...")
    total_samples = 0
    for idx, row in grade_df.iterrows():
        payload = {
            "device_id": f"SIM-{row['paciente_id']}",
            "paciente_id": row['paciente_id'],
            "cama_id": row['paciente_id'],
            "postura": row['postura'],
            "confianca": float(random.uniform(0.8, 1.0)),
            "amostra_ms": int(passo_min * 60 * 1000),
            "ts_utc": str(pd.to_datetime(row['timestamp']).to_pydatetime()),
        }
        try:
            ev = _normalizar_payload(payload, None)
            _registrar_evento(ev)
            total_samples += 1
        except Exception as exc:
            print(f"Failed to register sample for {row['paciente_id']} at {row['timestamp']}: {exc}")
    print(f"Inserted {total_samples} samples.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--patients", type=int, default=3, help="Number of simulated patients")
    p.add_argument("--hours", type=int, default=6, help="Duration in hours for each session")
    p.add_argument("--passo-min", type=int, dest="passo_min", default=5, help="Sampling step in minutes")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    args = p.parse_args()

    main(args.patients, args.hours, args.passo_min, args.seed)
