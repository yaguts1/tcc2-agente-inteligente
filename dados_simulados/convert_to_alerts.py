# -*- coding: utf-8 -*-
"""Converte eventos de postura em registros de alerta para testar o frontend.

Lê um CSV de eventos gerado por `gerador.gerar_eventos_sessao` (tem colunas como
`paciente_id, timestamp, postura, duracao_min, origem, falha, inicio, fim`) e produz
um CSV/JSONL de alertas compatível com o formato que o frontend espera.

Uso (exemplo):
    python -m dados_simulados.convert_to_alerts --input dados_simulados/gerados_ui/PAC-0001_eventos_36h_seed42_*.csv

Saída: escreve em `dados_simulados/gerados_ui/` um arquivo `*_alerts_*.csv` e `*_alerts_*.jsonl`.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import json
import pandas as pd
from typing import Optional


DEFAULT_THRESHOLD_MIN = 120  # minutes; if an event duracao_min >= this -> candidate alert
DEFAULT_ROOM = "---"
DEFAULT_BED = "---"


def detect_input_path(pattern: str) -> Path:
    p = Path('.').resolve()
    matches = list(p.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No files match pattern: {pattern}")
    # pick the first (or allow user to pass explicit path)
    return matches[0]


def to_iso(ts: Optional[pd.Timestamp]) -> Optional[str]:
    if pd.isna(ts) or ts is None:
        return None
    if isinstance(ts, str):
        return pd.to_datetime(ts).isoformat()
    return pd.to_datetime(ts).isoformat()


def convert_events(df: pd.DataFrame, paciente_id: str, threshold_min: int = DEFAULT_THRESHOLD_MIN) -> pd.DataFrame:
    alerts = []

    # ensure datetime columns
    if 'inicio' in df.columns:
        df['inicio'] = pd.to_datetime(df['inicio'])
    elif 'timestamp' in df.columns:
        df['inicio'] = pd.to_datetime(df['timestamp'])

    # prefer explicit duracao_min column
    if 'duracao_min' not in df.columns:
        raise ValueError('Input eventos CSV must have duracao_min column')

    for idx, row in df.iterrows():
        dur = float(row.get('duracao_min', 0.0))
        falha = bool(row.get('falha', False))
        inicio = row.get('inicio')

        # Mark candidate if falha or exceeded threshold
        if falha or dur >= threshold_min:
            # risk based on how much above threshold
            if dur >= 2.0 * threshold_min:
                risk = 'high'
            elif dur >= 1.5 * threshold_min:
                risk = 'medium'
            else:
                risk = 'low'

            last_repos = to_iso(inicio)
            # next repositioning expected at inicio + threshold
            next_repos = (pd.to_datetime(inicio) + pd.Timedelta(minutes=threshold_min)).isoformat()

            alert = {
                'id': f"{paciente_id}_{idx}",
                'patientName': paciente_id,
                'room': DEFAULT_ROOM,
                'bed': DEFAULT_BED,
                'lastRepositioning': last_repos,
                'nextRepositioning': next_repos,
                'riskLevel': risk,
                'status': 'pending',
            }
            alerts.append(alert)

    return pd.DataFrame(alerts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Converter eventos -> alerts for UI')
    parser.add_argument('--input', '-i', required=True, help='Input eventos CSV path or glob pattern')
    parser.add_argument('--threshold', '-t', type=int, default=DEFAULT_THRESHOLD_MIN, help='Threshold minutes to flag alert')
    parser.add_argument('--outdir', '-o', default='dados_simulados/gerados_ui', help='Output directory')
    args = parser.parse_args(argv)

    # resolve input path (glob allowed)
    input_path = Path(args.input)
    if any(ch in args.input for ch in ['*', '?', '[']):
        input_path = detect_input_path(args.input)

    df = pd.read_csv(input_path)

    # infer paciente_id column or from filename
    if 'paciente_id' in df.columns:
        paciente_id = df.loc[0, 'paciente_id']
    else:
        # try to parse from filename
        stem = input_path.stem
        if stem.startswith('PAC-'):
            paciente_id = stem.split('_')[0]
        else:
            paciente_id = 'PAC-0001'

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    alerts_df = convert_events(df, paciente_id, threshold_min=args.threshold)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = out_dir / f"{paciente_id}_alerts_threshold{args.threshold}_{ts}.csv"
    jsonl_path = out_dir / f"{paciente_id}_alerts_threshold{args.threshold}_{ts}.jsonl"

    alerts_df.to_csv(csv_path, index=False)

    with open(jsonl_path, 'w', encoding='utf-8') as fh:
        for rec in alerts_df.to_dict(orient='records'):
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    print('Wrote:', csv_path)
    print('Wrote:', jsonl_path)
    print(f'Generated {len(alerts_df)} alerts')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
