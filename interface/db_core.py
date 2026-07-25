"""Core database connection and helper functions."""
from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd

from interface.tempo import agora_utc_naive

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
    """`agora` em UTC naive, no mesmo referencial dos timestamps do banco.

    Usava datetime.now() (hora LOCAL) apesar do nome: com TZ=America/Sao_Paulo
    isso gravava created_at/updated_at, as janelas de device_assignments e
    paciente_cama_history 3h deslocados dos ts_ms com que são comparados em
    resolver_paciente_por_device_em() — a query que decide de qual paciente é
    uma leitura de sensor.
    """
    return agora_utc_naive().strftime(ISO_FORMAT)

def norm_iso(series: pd.Series) -> pd.Series:
    s = pd.to_datetime(series, errors="coerce", utc=False)
    if getattr(s.dtype, "tz", None) is not None:
        s = s.dt.tz_convert(None)
    s = s.dt.floor("s")
    formatted = s.dt.strftime(ISO_FORMAT).astype("object")
    formatted[formatted == "NaT"] = None
    return formatted


def ensure_paciente(conn: sqlite3.Connection, paciente_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (paciente_id,))


def _ensure_grade_confianca_column(conn: sqlite3.Connection) -> None:
    """Add confianca column to grade table if it doesn't exist.

    Redundante para bancos criados via migrations/0001_baseline.sql (que já
    inclui a coluna), mas mantido como checagem defensiva de baixo custo
    para quem chama inserir_grade diretamente (ver interface/repositories/grade.py).
    """
    info = conn.execute("PRAGMA table_info(grade)").fetchall()
    colunas = {str(row["name"]) for row in info}
    if "confianca" not in colunas:
        conn.execute("ALTER TABLE grade ADD COLUMN confianca REAL")
    conn.commit()


def criar_esquema(db_path: str = "dados.db") -> None:
    """Garante que o schema do banco está atualizado, aplicando as
    migrations pendentes (ver migrations/runner.py). Substituiu o antigo
    executescript inline + 3 funções ad-hoc de "a coluna existe?" — agora
    mudanças de schema são migrations versionadas e numeradas.
    """
    from migrations.runner import upgrade

    upgrade(db_path)
