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


def ensure_paciente(conn: sqlite3.Connection, paciente_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (paciente_id,))


def _ensure_cama_column(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(paciente_fichas)").fetchall()
    colunas = {str(row["name"]) for row in info}
    if "cama_id" not in colunas:
        conn.execute("ALTER TABLE paciente_fichas ADD COLUMN cama_id TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pac_fichas_cama ON paciente_fichas (cama_id) WHERE cama_id IS NOT NULL"
    )


def _ensure_users_role_column(conn: sqlite3.Connection) -> None:
    """Add role column to users table if it doesn't exist."""
    info = conn.execute("PRAGMA table_info(users)").fetchall()
    colunas = {str(row["name"]) for row in info}
    if "role" not in colunas:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'staff'")
    conn.commit()


def _ensure_grade_confianca_column(conn: sqlite3.Connection) -> None:
    """Add confianca column to grade table if it doesn't exist."""
    info = conn.execute("PRAGMA table_info(grade)").fetchall()
    colunas = {str(row["name"]) for row in info}
    if "confianca" not in colunas:
        conn.execute("ALTER TABLE grade ADD COLUMN confianca REAL")
    conn.commit()


def criar_esquema(db_path: str = "dados.db") -> None:
    """Cria o schema base de tabelas e indices se ainda nao existirem."""
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pacientes (
                id TEXT PRIMARY KEY
            );
              CREATE TABLE IF NOT EXISTS paciente_fichas (
                  paciente_id TEXT PRIMARY KEY,
                  nome TEXT NOT NULL,
                  perfil TEXT NOT NULL,
                  cama_id TEXT,
                  observacoes TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
              );
            CREATE TABLE IF NOT EXISTS paciente_rotinas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id TEXT NOT NULL,
                label TEXT NOT NULL,
                inicio TEXT NOT NULL,
                duracao_min INT NOT NULL,
                descricao TEXT,
                ativo INT NOT NULL DEFAULT 1,
                sort_order INT NOT NULL DEFAULT 0,
                UNIQUE(paciente_id, label, inicio),
                FOREIGN KEY(paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS paciente_documentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id TEXT NOT NULL,
                nome_arquivo TEXT NOT NULL,
                caminho TEXT NOT NULL,
                observacao TEXT,
                enviado_em TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_documentos_paciente
                ON paciente_documentos (paciente_id, enviado_em);
            CREATE TABLE IF NOT EXISTS grade (
                paciente_id TEXT,
                ts TEXT,
                postura TEXT,
                PRIMARY KEY (paciente_id, ts)
            );
            CREATE TABLE IF NOT EXISTS eventos (
                paciente_id TEXT,
                inicio TEXT,
                fim TEXT,
                tipo TEXT,
                PRIMARY KEY (paciente_id, inicio)
            );
            CREATE TABLE IF NOT EXISTS alertas (
                paciente_id TEXT,
                inicio TEXT,
                fim TEXT,
                tipo TEXT,
                perfil TEXT,
                janela_min INT,
                status TEXT,
                duracao_min REAL,
                CHECK (status IN ('aberto','reconhecido','fechado')),
                CHECK (tipo IN ('imobilidade')),
                PRIMARY KEY (paciente_id, inicio)
            );
              CREATE INDEX IF NOT EXISTS idx_pac_fichas_nome ON paciente_fichas (nome);
              CREATE UNIQUE INDEX IF NOT EXISTS idx_pac_fichas_cama ON paciente_fichas (cama_id) WHERE cama_id IS NOT NULL;
              CREATE INDEX IF NOT EXISTS idx_rotinas_paciente ON paciente_rotinas (paciente_id, inicio);
            CREATE INDEX IF NOT EXISTS idx_grade_paciente_ts
                ON grade (paciente_id, ts);
            CREATE INDEX IF NOT EXISTS idx_alertas_status
                ON alertas (paciente_id, status);
            CREATE INDEX IF NOT EXISTS idx_alertas_inicio
                ON alertas (inicio);
            CREATE INDEX IF NOT EXISTS idx_alertas_paciente_inicio
                ON alertas (paciente_id, inicio);
            CREATE INDEX IF NOT EXISTS idx_eventos_inicio
                ON eventos (inicio);

            -- Índices compostos adicionais para queries frequentes
            CREATE INDEX IF NOT EXISTS idx_alertas_status_inicio
                ON alertas (status, inicio DESC);
            CREATE INDEX IF NOT EXISTS idx_alertas_paciente_status_inicio
                ON alertas (paciente_id, status, inicio DESC);
            CREATE INDEX IF NOT EXISTS idx_grade_paciente_ts_desc
                ON grade (paciente_id, ts DESC);
            CREATE INDEX IF NOT EXISTS idx_eventos_paciente_inicio
                ON eventos (paciente_id, inicio DESC);

            CREATE TABLE IF NOT EXISTS timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id TEXT,
                ts TEXT NOT NULL,
                ts_ms INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                descricao TEXT,
                meta TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_timeline_paciente_ts_ms_desc ON timeline_events (paciente_id, ts_ms DESC);
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                meta TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS device_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                cama_id TEXT,
                paciente_id TEXT,
                start_ts TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ts TEXT,
                end_ms INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_device_assign_device_start ON device_assignments (device_id, start_ms);
            CREATE INDEX IF NOT EXISTS idx_device_assign_cama_start ON device_assignments (cama_id, start_ms);
            CREATE TABLE IF NOT EXISTS paciente_cama_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id TEXT NOT NULL,
                cama_id TEXT NOT NULL,
                start_ts TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ts TEXT,
                end_ms INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_paciente_cama_start ON paciente_cama_history (paciente_id, start_ms);
            CREATE INDEX IF NOT EXISTS idx_cama_paciente_start ON paciente_cama_history (cama_id, start_ms);
            CREATE TABLE IF NOT EXISTS device_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                ts_ms INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                processed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_device_events_device_ts ON device_events (device_id, ts_ms);
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at);
            """
        )
        _ensure_cama_column(conn)
        _ensure_users_role_column(conn)
        _ensure_grade_confianca_column(conn)
        conn.commit()
