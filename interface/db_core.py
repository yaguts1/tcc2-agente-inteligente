"""Core database connection and helper functions."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

def ensure_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if path.suffix == "" and not path.name:
        raise ValueError("Caminho do banco de dados invalido.")
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path

def connect(db_path: str) -> sqlite3.Connection:
    path = ensure_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # WAL reduz contencao entre leituras e escritas concorrentes (mesmo numa
    # unica instancia, o app tem WebSocket + reconciler + requests HTTP
    # escrevendo/lendo ao mesmo tempo).
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def utc_now_iso() -> str:
    return datetime.now().replace(microsecond=0).strftime(ISO_FORMAT)

def norm_iso(series: pd.Series) -> pd.Series:
    s = pd.to_datetime(series, errors="coerce", utc=False)
    if getattr(s.dtype, "tz", None) is not None:
        s = s.dt.tz_convert(None)
    s = s.dt.floor("s")
    formatted = s.dt.strftime(ISO_FORMAT).astype("object")
    formatted[formatted == "NaT"] = None
    return formatted
