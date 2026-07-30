#!/usr/bin/env python3
"""Convert frontend-generated alerts/events or the generator output into a firmware-ready eventos.jsonl

This script reads JSONL or CSV files containing events or frontend-shaped alerts and produces
an NDJSON file suitable to copy into `firmware/esp32_replay/data/eventos.jsonl`.

It ensures fields: device_id, paciente_id, cama_id, postura, confianca, amostra_ms, ts_utc.
Optionally appends a trailing 'Z' to ts_utc to make timestamps explicit UTC.

Usage:
  python -m tools.convert_for_firmware -i input.jsonl -o firmware/eventos.jsonl --device DEV-001 --cama C-01 --add-z

"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from collections.abc import Iterable
import pandas as pd


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open('r', encoding='utf-8') as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            yield json.loads(ln)


def read_csv(path: Path) -> Iterable[dict[str, Any]]:
    df = pd.read_csv(path)
    yield from df.to_dict(orient='records')


def normalize_ts(ts: str, add_z: bool) -> str:
    # Use pandas to parse flexible forms; output ISO without ms
    ts_parsed = pd.to_datetime(ts)
    out = ts_parsed.floor('s').strftime('%Y-%m-%dT%H:%M:%S')
    if add_z:
        out = out + 'Z'
    return out


def map_record(rec: dict[str, Any], device: str, paciente: str | None, cama: str | None, add_z: bool) -> dict[str, Any]:
    # Prefer explicit fields if present
    postura = rec.get('postura') or rec.get('style') or rec.get('position') or 'supino'
    confianca = float(rec.get('confianca') or rec.get('confidence') or 0.9)
    amostra_ms = int(rec.get('amostra_ms') or rec.get('sample_ms') or 60000)
    ts_raw = rec.get('ts_utc') or rec.get('timestamp') or rec.get('lastRepositioning') or rec.get('time')
    if not ts_raw:
        raise ValueError('No timestamp field present in record')
    ts_iso = normalize_ts(ts_raw, add_z)

    return {
        "device_id": device,
        "paciente_id": paciente or rec.get('paciente_id') or rec.get('patientName') or None,
        "cama_id": cama or rec.get('cama_id') or rec.get('cama') or None,
        "postura": str(postura),
        "confianca": float(confianca),
        "amostra_ms": int(amostra_ms),
        "ts_utc": ts_iso,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Convert input files to firmware eventos.jsonl')
    parser.add_argument('-i', '--input', required=True, help='Input file path (JSONL or CSV)')
    parser.add_argument('-o', '--output', required=True, help='Output NDJSON file path')
    parser.add_argument('--device', required=True, help='device_id to inject')
    parser.add_argument('--paciente', help='Default paciente_id to inject')
    parser.add_argument('--cama', help='Default cama_id to inject')
    parser.add_argument('--add-z', action='store_true', help='Append trailing Z to timestamps')
    args = parser.parse_args(argv)

    p = Path(args.input)
    if not p.exists():
        print('Input not found:', p)
        return 2

    if p.suffix.lower() == '.jsonl' or p.suffix.lower() == '.ndjson':
        records = list(read_jsonl(p))
    elif p.suffix.lower() in {'.csv', '.tsv'}:
        records = list(read_csv(p))
    else:
        # try JSONL fallback
        records = list(read_jsonl(p))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open('w', encoding='utf-8') as fh:
        for rec in records:
            try:
                mapped = map_record(rec, args.device, args.paciente, args.cama, args.add_z)
            except Exception as exc:
                print('Skipping record due to error:', exc)
                continue
            fh.write(json.dumps(mapped, ensure_ascii=False) + '\n')

    print(f'Wrote {out_path} ({len(records)} input records)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
