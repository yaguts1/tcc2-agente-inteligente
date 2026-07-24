"""Camada simples de persistencia SQLite para dados de simulacao e fichas de pacientes."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"
_VALID_TABLES = {"grade", "eventos", "alertas"}
PACIENTE_ID_PREFIX = "PAC"
DEFAULT_ROTINA_DURACAO_MIN = 30
PERFIS_VALIDOS = {"baixo", "medio", "alto"}


def _ensure_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if path.suffix == "" and not path.name:
        raise ValueError("Caminho do banco de dados invalido.")
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(db_path: str) -> sqlite3.Connection:
    path = _ensure_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _norm_iso(series: pd.Series) -> pd.Series:
    s = pd.to_datetime(series, errors="coerce", utc=False)
    if getattr(s.dtype, "tz", None) is not None:
        s = s.dt.tz_convert(None)
    s = s.dt.floor("s")
    formatted = s.dt.strftime(ISO_FORMAT).astype("object")
    formatted[formatted == "NaT"] = None
    return formatted


def _ensure_paciente(conn: sqlite3.Connection, paciente_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (paciente_id,))


def _utc_now_iso() -> str:
    return datetime.now().replace(microsecond=0).strftime(ISO_FORMAT)


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


def _generate_paciente_id(conn: sqlite3.Connection, prefix: str = PACIENTE_ID_PREFIX) -> str:
    existing_ids = {str(row[0]) for row in conn.execute("SELECT id FROM pacientes")}
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    maior = 0
    for pid in existing_ids:
        match = pattern.match(pid)
        if match:
            maior = max(maior, int(match.group(1)))
    while True:
        maior += 1
        candidate = f"{prefix}-{maior:04d}"
        if candidate not in existing_ids:
            return candidate


def _normalize_cama_id(valor: str | None) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _assert_cama_disponivel(
    conn: sqlite3.Connection,
    cama_id: str | None,
    *,
    ignorar_paciente: str | None = None,
) -> None:
    if cama_id is None:
        return
    cursor = conn.execute(
        "SELECT paciente_id FROM paciente_fichas WHERE cama_id = ?",
        (cama_id,),
    )
    row = cursor.fetchone()
    if row is not None:
        existente = str(row["paciente_id"])
        if ignorar_paciente is None or existente != ignorar_paciente:
            raise ValueError(f"Cama '{cama_id}' ja esta atribuida ao paciente {existente}.")


def _normalize_hhmm(valor: str) -> str:
    texto = str(valor or "").strip()
    if not texto:
        raise ValueError("Horario de rotina invalido.")
    partes = texto.split(":")
    if len(partes) != 2:
        raise ValueError(f"Horario '{texto}' deve estar no formato HH:MM.")
    try:
        hora = int(partes[0])
        minuto = int(partes[1])
    except ValueError as exc:
        raise ValueError(f"Horario '{texto}' deve conter numeros validos.") from exc
    if not (0 <= hora <= 23 and 0 <= minuto <= 59):
        raise ValueError(f"Horario '{texto}' fora do intervalo 00:00-23:59.")
    return f"{hora:02d}:{minuto:02d}"


def _prepare_rotinas(rotinas: Sequence[dict] | None) -> List[dict]:
    if not rotinas:
        return []
    preparados: List[dict] = []
    for ordem, raw in enumerate(rotinas):
        if raw is None:
            continue
        label = str(raw.get("label", "")).strip()
        if not label:
            continue
        inicio_val = _normalize_hhmm(raw.get("inicio", ""))
        try:
            duracao = int(raw.get("duracao_min", DEFAULT_ROTINA_DURACAO_MIN))
        except (TypeError, ValueError):
            duracao = DEFAULT_ROTINA_DURACAO_MIN
        if duracao <= 0:
            duracao = DEFAULT_ROTINA_DURACAO_MIN
        descricao_raw = raw.get("descricao")
        descricao_val = None if descricao_raw is None else str(descricao_raw).strip() or None
        ativo_flag = raw.get("ativo", True)
        ativo_val = 0 if ativo_flag in (False, 0, "0") else 1
        sort_order = raw.get("sort_order")
        try:
            sort_idx = int(sort_order)
        except (TypeError, ValueError):
            sort_idx = ordem
        preparados.append(
            {
                "label": label,
                "inicio": inicio_val,
                "duracao_min": duracao,
                "descricao": descricao_val,
                "ativo": ativo_val,
                "sort_order": sort_idx,
            }
        )
    return preparados


def _replace_rotinas(conn: sqlite3.Connection, paciente_id: str, rotinas: Sequence[dict] | None) -> None:
    normalizadas = _prepare_rotinas(rotinas)
    conn.execute("DELETE FROM paciente_rotinas WHERE paciente_id = ?", (paciente_id,))
    if not normalizadas:
        return
    conn.executemany(
        """
        INSERT INTO paciente_rotinas (paciente_id, label, inicio, duracao_min, descricao, ativo, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                paciente_id,
                item["label"],
                item["inicio"],
                item["duracao_min"],
                item["descricao"],
                item["ativo"],
                item["sort_order"],
            )
            for item in normalizadas
        ],
    )


def _fetch_rotinas(conn: sqlite3.Connection, paciente_id: str) -> List[dict]:
    cursor = conn.execute(
        """
        SELECT id, label, inicio, duracao_min, descricao, ativo, sort_order
        FROM paciente_rotinas
        WHERE paciente_id = ?
        ORDER BY sort_order, inicio
        """,
        (paciente_id,),
    )
    rows = cursor.fetchall()
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "inicio": row["inicio"],
            "duracao_min": row["duracao_min"],
            "descricao": row["descricao"],
            "ativo": bool(row["ativo"]),
            "sort_order": row["sort_order"],
        }
        for row in rows
    ]




def listar_documentos(db_path: str, paciente_id: str) -> List[dict]:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT id, paciente_id, nome_arquivo, caminho, observacao, enviado_em
            FROM paciente_documentos
            WHERE paciente_id = ?
            ORDER BY enviado_em DESC, id DESC
            """,
            (paciente_id,),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def registrar_documento(
    db_path: str,
    paciente_id: str,
    nome_arquivo: str,
    caminho: str,
    observacao: str | None = None,
) -> int:
    nome_limpo = str(nome_arquivo or '').strip()
    if not nome_limpo:
        raise ValueError('Nome do arquivo nao pode ser vazio.')
    caminho_limpo = str(caminho or '').strip()
    if not caminho_limpo:
        raise ValueError('Caminho do arquivo deve ser informado.')
    obs_val = None if observacao is None else str(observacao).strip() or None
    agora_iso = _utc_now_iso()
    with _connect(db_path) as conn:
        _ensure_paciente(conn, paciente_id)
        cursor = conn.execute(
            """
            INSERT INTO paciente_documentos (paciente_id, nome_arquivo, caminho, observacao, enviado_em)
            VALUES (?, ?, ?, ?, ?)
            """,
            (paciente_id, nome_limpo, caminho_limpo, obs_val, agora_iso),
        )
        return cursor.lastrowid


def remover_documento(db_path: str, documento_id: int) -> Dict[str, str] | None:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            'SELECT paciente_id, caminho FROM paciente_documentos WHERE id = ?',
            (documento_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        conn.execute('DELETE FROM paciente_documentos WHERE id = ?', (documento_id,))
    return {'paciente_id': row['paciente_id'], 'caminho': row['caminho']}


def obter_documento(db_path: str, documento_id: int) -> dict | None:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            'SELECT id, paciente_id, nome_arquivo, caminho, observacao, enviado_em FROM paciente_documentos WHERE id = ?',
            (documento_id,),
        )
        row = cursor.fetchone()
    return None if row is None else dict(row)


def criar_esquema(db_path: str = "dados.db") -> None:
    """Cria o schema base de tabelas e indices se ainda nao existirem."""
    with _connect(db_path) as conn:
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


def criar_usuario(db_path: str, username: str, password_hash: str, display_name: str | None = None) -> None:
    """Cria um usuario novo. Levanta ValueError se ja existir."""
    uname = str(username or "").strip()
    if not uname:
        raise ValueError("username invalido")
    ph = str(password_hash or "").strip()
    if not ph:
        raise ValueError("password_hash necessario")
    disp = None if display_name is None else str(display_name).strip() or None
    agora = _utc_now_iso()
    with _connect(db_path) as conn:
        cur = conn.execute("SELECT username FROM users WHERE username = ?", (uname,))
        if cur.fetchone() is not None:
            raise ValueError("usuario ja existe")
        conn.execute("INSERT INTO users (username, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)", (uname, ph, disp, agora))
        conn.commit()


def obter_usuario_por_nome(db_path: str, username: str) -> dict | None:
    uname = str(username or "").strip()
    if not uname:
        return None
    with _connect(db_path) as conn:
        cur = conn.execute("SELECT username, password_hash, display_name, created_at, role FROM users WHERE username = ?", (uname,))
        row = cur.fetchone()
    return None if row is None else dict(row)


def proximo_identificador_paciente(db_path: str, prefixo: str = PACIENTE_ID_PREFIX) -> str:
    with _connect(db_path) as conn:
        return _generate_paciente_id(conn, prefix=prefixo)


def listar_fichas_pacientes(db_path: str, incluir_rotinas: bool = False) -> List[dict]:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at
            FROM paciente_fichas
            ORDER BY nome COLLATE NOCASE, paciente_id
            """
        )
        fichas = []
        for row in cursor.fetchall():
            ficha = dict(row)
            if incluir_rotinas:
                ficha["rotinas"] = _fetch_rotinas(conn, ficha["paciente_id"])
            fichas.append(ficha)
        return fichas


def obter_ficha_paciente(
    db_path: str,
    paciente_id: str,
    incluir_rotinas: bool = False,
) -> dict | None:
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at
            FROM paciente_fichas
            WHERE paciente_id = ?
            """,
            (paciente_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        ficha = dict(row)
        if incluir_rotinas:
            ficha["rotinas"] = _fetch_rotinas(conn, paciente_id)
        return ficha


def obter_ficha_por_cama(
    db_path: str,
    cama_id: str,
    incluir_rotinas: bool = False,
) -> dict | None:
    cama_norm = _normalize_cama_id(cama_id)
    if cama_norm is None:
        return None
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at
            FROM paciente_fichas
            WHERE cama_id = ?
            """,
            (cama_norm,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        ficha = dict(row)
        if incluir_rotinas:
            ficha["rotinas"] = _fetch_rotinas(conn, ficha["paciente_id"])
        return ficha


def criar_paciente(
    db_path: str,
    nome: str,
    perfil: str,
    cama_id: str | None = None,
    observacoes: str | None = None,
    rotinas: Sequence[dict] | None = None,
) -> dict:
    nome_limpo = str(nome or "").strip()
    if not nome_limpo:
        raise ValueError("Nome do paciente nao pode ser vazio.")
    perfil_norm = str(perfil or "").strip().lower()
    if perfil_norm not in PERFIS_VALIDOS:
        raise ValueError(f"Perfil invalido: {perfil}.")
    cama_norm = _normalize_cama_id(cama_id)
    obs_val = None if observacoes is None else str(observacoes).strip() or None
    with _connect(db_path) as conn:
        _assert_cama_disponivel(conn, cama_norm)
        paciente_id = _generate_paciente_id(conn)
        agora_iso = _utc_now_iso()
        conn.execute("INSERT INTO pacientes (id) VALUES (?)", (paciente_id,))
        conn.execute(
            """
            INSERT INTO paciente_fichas (paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (paciente_id, nome_limpo, perfil_norm, cama_norm, obs_val, agora_iso, agora_iso),
        )
        _replace_rotinas(conn, paciente_id, rotinas)
        # If a cama was provided, register initial paciente->cama history
        if cama_norm is not None:
            # use same timestamp used for created_at
            start_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
            conn.execute(
                "INSERT INTO paciente_cama_history (paciente_id, cama_id, start_ts, start_ms) VALUES (?, ?, ?, ?)",
                (paciente_id, cama_norm, agora_iso, start_ms),
            )
            # if there is a device currently assigned to this cama, bind it to the paciente
            try:
                cur = conn.execute(
                    "SELECT device_id FROM device_assignments WHERE cama_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
                    (cama_norm,),
                )
                row = cur.fetchone()
                if row is not None:
                    device_id = row["device_id"]
                    # start a new device_assignment that links this device to the paciente
                    now_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
                    conn.execute(
                        "UPDATE device_assignments SET end_ts = ?, end_ms = ? WHERE device_id = ? AND end_ms IS NULL",
                        (agora_iso, now_ms, device_id),
                    )
                    conn.execute(
                        "INSERT INTO device_assignments (device_id, cama_id, paciente_id, start_ts, start_ms) VALUES (?, ?, ?, ?, ?)",
                        (device_id, cama_norm, paciente_id, agora_iso, now_ms),
                    )
            except Exception:
                # non-fatal: do not prevent patient creation
                pass
        conn.commit()
    return obter_ficha_paciente(db_path, paciente_id, incluir_rotinas=True)  # type: ignore[return-value]


def atualizar_paciente(
    db_path: str,
    paciente_id: str,
    nome: str,
    perfil: str,
    cama_id: str | None = None,
    observacoes: str | None = None,
    rotinas: Sequence[dict] | None = None,
) -> dict:
    nome_limpo = str(nome or "").strip()
    if not nome_limpo:
        raise ValueError("Nome do paciente nao pode ser vazio.")
    perfil_norm = str(perfil or "").strip().lower()
    if perfil_norm not in PERFIS_VALIDOS:
        raise ValueError(f"Perfil invalido: {perfil}.")
    cama_norm = _normalize_cama_id(cama_id)
    obs_val = None if observacoes is None else str(observacoes).strip() or None
    with _connect(db_path) as conn:
        # fetch existing ficha to detect cama changes
        cur = conn.execute(
            "SELECT paciente_id, cama_id FROM paciente_fichas WHERE paciente_id = ?",
            (paciente_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError("Paciente nao encontrado.")
        existing_cama = row["cama_id"]
        _assert_cama_disponivel(conn, cama_norm, ignorar_paciente=paciente_id)
        agora_iso = _utc_now_iso()
        conn.execute(
            """
            UPDATE paciente_fichas
            SET nome = ?, perfil = ?, cama_id = ?, observacoes = ?, updated_at = ?
            WHERE paciente_id = ?
            """,
            (nome_limpo, perfil_norm, cama_norm, obs_val, agora_iso, paciente_id),
        )
        if rotinas is not None:
            _replace_rotinas(conn, paciente_id, rotinas)
        # if cama changed, close previous history and create new history entry
        try:
            if (existing_cama or None) != (cama_norm or None):
                # close last open history for this paciente (if any)
                cur2 = conn.execute(
                    "SELECT id, start_ms FROM paciente_cama_history WHERE paciente_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
                    (paciente_id,),
                )
                r2 = cur2.fetchone()
                now_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
                if r2 is not None:
                    aid = int(r2["id"])
                    conn.execute(
                        "UPDATE paciente_cama_history SET end_ts = ?, end_ms = ? WHERE id = ?",
                        (agora_iso, now_ms, aid),
                    )
                # start new history if new cama provided
                if cama_norm is not None:
                    conn.execute(
                        "INSERT INTO paciente_cama_history (paciente_id, cama_id, start_ts, start_ms) VALUES (?, ?, ?, ?)",
                        (paciente_id, cama_norm, agora_iso, now_ms),
                    )
                    # if there is a device currently assigned to this cama, bind it to the paciente
                    try:
                        cur = conn.execute(
                            "SELECT device_id FROM device_assignments WHERE cama_id = ? AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
                            (cama_norm,),
                        )
                        row = cur.fetchone()
                        if row is not None:
                            device_id = row["device_id"]
                            # close previous open assignment and start new one linking device->paciente
                            conn.execute(
                                "UPDATE device_assignments SET end_ts = ?, end_ms = ? WHERE device_id = ? AND end_ms IS NULL",
                                (agora_iso, now_ms, device_id),
                            )
                            conn.execute(
                                "INSERT INTO device_assignments (device_id, cama_id, paciente_id, start_ts, start_ms) VALUES (?, ?, ?, ?, ?)",
                                (device_id, cama_norm, paciente_id, agora_iso, now_ms),
                            )
                    except Exception:
                        pass
        except Exception:
            # non-fatal: keep patient update even if history logging fails
            pass
        conn.commit()
    ficha = obter_ficha_paciente(db_path, paciente_id, incluir_rotinas=True)
    if ficha is None:
        raise LookupError("Paciente nao encontrado apos atualizacao.")
    return ficha


def inserir_grade(
    db_path: str,
    df_grade: pd.DataFrame,
    paciente_id: str = "P1",
) -> int:
    """Insere amostras da grade simulada."""
    required = {"timestamp", "postura"}
    if not required.issubset(df_grade.columns):
        raise ValueError("df_grade precisa conter as colunas 'timestamp' e 'postura'.")

    timestamps = _norm_iso(df_grade["timestamp"]).tolist()
    posturas = df_grade["postura"].astype(str).tolist()
    
    # Handle optional confianca
    if "confianca" in df_grade.columns:
        confiancas = df_grade["confianca"].fillna(1.0).tolist()
    else:
        confiancas = [1.0] * len(timestamps)

    registros = [
        (paciente_id, ts, postura, conf)
        for ts, postura, conf in zip(timestamps, posturas, confiancas)
        if ts is not None
    ]

    if not registros:
        return 0

    with _connect(db_path) as conn:
        _ensure_paciente(conn, paciente_id)
        _ensure_grade_confianca_column(conn)
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO grade (paciente_id, ts, postura, confianca) VALUES (?, ?, ?, ?)",
            registros,
        )
        return conn.total_changes - before


def inserir_eventos(
    db_path: str,
    df_eventos: pd.DataFrame,
    paciente_id: str = "P1",
) -> int:
    """Insere eventos simulados em lote."""
    required = {"inicio", "fim"}
    if not required.issubset(df_eventos.columns):
        raise ValueError("df_eventos precisa conter as colunas 'inicio' e 'fim'.")

    tipo_col = "tipo" if "tipo" in df_eventos.columns else "origem"
    if tipo_col not in df_eventos.columns:
        raise ValueError("df_eventos precisa conter a coluna 'tipo' ou 'origem'.")

    inicios = _norm_iso(df_eventos["inicio"]).tolist()
    fins = _norm_iso(df_eventos["fim"]).tolist()
    tipos = df_eventos[tipo_col].astype(str).tolist()

    registros = [
        (paciente_id, inicio, fim, tipo)
        for inicio, fim, tipo in zip(inicios, fins, tipos)
        if inicio is not None
    ]

    if not registros:
        return 0

    with _connect(db_path) as conn:
        _ensure_paciente(conn, paciente_id)
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO eventos (paciente_id, inicio, fim, tipo) VALUES (?, ?, ?, ?)",
            registros,
        )
        return conn.total_changes - before


def inserir_alertas(
    db_path: str,
    alertas: List[dict],
) -> int:
    """Insere ou atualiza alertas calculados pelo motor."""
    if not alertas:
        return 0

    required = {"paciente_id", "inicio", "tipo", "perfil", "janela_min", "status"}
    for alerta in alertas:
        if not required.issubset(alerta):
            raise ValueError(
                "Alertas devem conter pelo menos paciente_id, inicio, tipo, perfil, janela_min e status."
            )

    inicio_series = _norm_iso(pd.Series([alerta.get("inicio") for alerta in alertas], dtype="object"))
    fim_series = _norm_iso(pd.Series([alerta.get("fim") for alerta in alertas], dtype="object"))

    registros = []
    pacientes: set[str] = set()
    for idx, alerta in enumerate(alertas):
        paciente_id = str(alerta["paciente_id"])
        inicio_val = inicio_series.iat[idx]
        if inicio_val is None:
            raise ValueError("Alertas precisam de 'inicio' valido para persistencia.")
        fim_val = fim_series.iat[idx]
        duracao = alerta.get("duracao_min")
        duracao_val = float(duracao) if duracao is not None else None
        registros.append(
            (
                paciente_id,
                inicio_val,
                fim_val,
                str(alerta.get("tipo", "")),
                str(alerta.get("perfil", "")),
                int(alerta.get("janela_min", 0)),
                str(alerta.get("status", "")),
                duracao_val,
            )
        )
        pacientes.add(paciente_id)

    if not registros:
        return 0

    with _connect(db_path) as conn:
        for paciente in pacientes:
            _ensure_paciente(conn, paciente)
        before = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO alertas
            (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros,
        )
        # number of DB changes caused by alert inserts only
        delta_alerts = conn.total_changes - before
        # For each alerta we persisted, add a timeline event so historical navigation
        # can reflect when alerts were generated. We insert an event with tipo 'alert_open'
        # using the inicio timestamp from the alerta payload and an epoch ms for easier queries.
        try:
            for idx, alerta in enumerate(alertas):
                paciente_id = str(alerta["paciente_id"]) if isinstance(alerta, dict) else registros[idx][0]
                inicio_val = inicio_series.iat[idx]
                status_val = str(alerta.get("status", "")) if isinstance(alerta, dict) else registros[idx][6]
                if inicio_val is None:
                    continue
                # only log opening events for alerts that are 'aberto' or were inserted now
                if status_val.lower() != "aberto":
                    continue
                ts_iso = inicio_val
                try:
                    ts_ms = int(pd.to_datetime(ts_iso).timestamp() * 1000)
                except Exception:
                    ts_ms = None
                if ts_ms is None:
                    continue
                conn.execute(
                    "INSERT INTO timeline_events (paciente_id, ts, ts_ms, tipo, descricao, meta) VALUES (?, ?, ?, ?, ?, ?)",
                    (paciente_id, ts_iso, ts_ms, "alert_open", None, None),
                )
        except Exception:
            # Do not fail alert insertion for timeline logging errors
            pass
        return int(delta_alerts)


def contar_por_paciente(db_path: str, tabela: str) -> Dict[str, int]:
    """Retorna a contagem de registros agrupada por paciente."""
    if tabela not in _VALID_TABLES:
        raise ValueError(f"Tabela desconhecida: {tabela}")

    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"SELECT paciente_id, COUNT(*) as total FROM {tabela} GROUP BY paciente_id"
        )
        rows = cursor.fetchall()
    return {str(row["paciente_id"]): int(row["total"]) for row in rows}


def listar_alertas_abertos(db_path: str) -> List[dict]:
    """Retorna alertas em aberto."""
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min"
            " FROM alertas WHERE status = ?",
            ("aberto",),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def selecionar_alertas_janela(db_path: str, horas: int | None = 24) -> list[dict]:
    """Busca alertas (qualquer status) dentro de uma janela de tempo.
    
    Args:
        db_path: Caminho do banco de dados
        horas: Janela de tempo em horas (se None, traz todos)
              Busca alertas de (agora - horas) até (agora + horas)
              
    Returns:
        Lista de dicts com dados dos alertas ordenados por inicio ASC
    """
    if horas is None:
        # Sem filtro de tempo - retorna todos
        with _connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
                "FROM alertas ORDER BY inicio ASC"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    # Com filtro de tempo - busca passado e futuro próximo
    agora = datetime.now().replace(microsecond=0)
    limite_inferior = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")
    limite_superior = (agora + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")

    with _connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
            "FROM alertas WHERE inicio >= ? AND inicio <= ? ORDER BY inicio ASC",
            (limite_inferior, limite_superior),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def selecionar_grade_janela(db_path: str, horas: int | None = 24) -> list[dict]:
    """Busca eventos de grade (postura) dentro de uma janela de tempo."""
    if horas is None:
        with _connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT paciente_id, ts, postura, confianca FROM grade ORDER BY ts ASC"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    agora = datetime.now().replace(microsecond=0)
    limite_inferior = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")
    limite_superior = (agora + timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")

    with _connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT paciente_id, ts, postura, confianca FROM grade WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
            (limite_inferior, limite_superior),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]



def listar_pacientes(db_path: str, horas: int | None = 24) -> list[str]:
    limite = None
    if horas is not None:
        agora = datetime.now().replace(microsecond=0)
        limite = (agora - timedelta(hours=horas)).strftime(ISO_FORMAT)
    with _connect(db_path) as conn:
        if limite is None:
            cur = conn.execute("SELECT DISTINCT paciente_id FROM alertas ORDER BY paciente_id")
        else:
            cur = conn.execute(
                "SELECT DISTINCT paciente_id FROM alertas WHERE inicio >= ? ORDER BY paciente_id",
                (limite,),
            )
        rows = cur.fetchall()
    return [str(row[0]) for row in rows]


def inserir_timeline_event(
    db_path: str,
    paciente_id: str,
    ts: str,
    ts_ms: int,
    tipo: str,
    descricao: str | None = None,
    meta: dict | None = None,
) -> int:
    """Insere um evento na timeline e retorna o id do registro inserido."""
    if not ts or ts_ms is None:
        raise ValueError("ts e ts_ms devem ser informados para inserir um evento de timeline.")
    meta_text = None if meta is None else json.dumps(meta, ensure_ascii=False)
    with _connect(db_path) as conn:
        # paciente_id may be None or empty for generic events; only ensure paciente when provided
        if paciente_id:
            _ensure_paciente(conn, paciente_id)
        cursor = conn.execute(
            "INSERT INTO timeline_events (paciente_id, ts, ts_ms, tipo, descricao, meta) VALUES (?, ?, ?, ?, ?, ?)",
            (paciente_id, ts, int(ts_ms), tipo, descricao, meta_text),
        )
        return int(cursor.lastrowid)


def selecionar_timeline(
    db_path: str,
    paciente_id: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1000,
    tipo: str | None = None,
) -> list[dict]:
    """Seleciona eventos da timeline aplicando filtros opcionais. Retorna lista de dicts.

    Ordena por `ts_ms` ascendente.
    """
    sql = "SELECT id, paciente_id, ts, ts_ms, tipo, descricao, meta, created_at FROM timeline_events"
    params: list = []
    where_clauses: list[str] = []
    if paciente_id:
        where_clauses.append("paciente_id = ?")
        params.append(paciente_id)
    if tipo:
        where_clauses.append("tipo = ?")
        params.append(tipo)
    if start_ms is not None:
        where_clauses.append("ts_ms >= ?")
        params.append(int(start_ms))
    if end_ms is not None:
        where_clauses.append("ts_ms <= ?")
        params.append(int(end_ms))
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    sql = f"{sql} ORDER BY ts_ms DESC LIMIT ?"
    params.append(int(limit))
    with _connect(db_path) as conn:
        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()
    results: list[dict] = []
    for row in rows:
        meta_val = row["meta"]
        try:
            meta_parsed = None if meta_val is None else json.loads(meta_val)
        except Exception:
            meta_parsed = None
        results.append(
            {
                "id": row["id"],
                "paciente_id": row["paciente_id"],
                "ts": row["ts"],
                "ts_ms": int(row["ts_ms"]),
                "tipo": row["tipo"],
                "descricao": row["descricao"],
                "meta": meta_parsed,
                "created_at": row["created_at"],
            }
        )
    return results


def alterar_status_alerta(
    db_path: str,
    paciente_id: str,
    inicio: str,
    status_destino: str,
    definir_fim: bool = False,
    now_dt: datetime | None = None,
) -> None:
    """Atualiza o status de um alerta e registra evento de timeline quando aplicavel.

    - status_destino: 'aberto'|'reconhecido'|'fechado'
    - if definir_fim is True, sets fim and duracao_min based on now_dt or current time.
    """
    if not paciente_id or not inicio:
        raise ValueError("paciente_id e inicio precisam ser informados")
    with _connect(db_path) as conn:
        cur = conn.execute(
            "SELECT paciente_id FROM alertas WHERE paciente_id = ? AND inicio = ?",
            (paciente_id, inicio),
        )
        if cur.fetchone() is None:
            raise LookupError("Alerta nao encontrado.")

        params = {"paciente_id": paciente_id, "inicio": inicio}
        if definir_fim:
            base_now = (now_dt or datetime.now()).replace(microsecond=0)
            ini_dt = datetime.fromisoformat(inicio[:19])
            fim_iso = base_now.strftime("%Y-%m-%dT%H:%M:%S")
            duracao_min = round((base_now - ini_dt).total_seconds() / 60.0, 2)
            conn.execute(
                """
                UPDATE alertas
                SET status = :status, fim = :fim, duracao_min = :duracao_min
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {
                    "status": status_destino,
                    "paciente_id": paciente_id,
                    "inicio": inicio,
                    "fim": fim_iso,
                    "duracao_min": duracao_min,
                },
            )
            # timeline log for alert close
            try:
                ts_iso = fim_iso
                ts_ms = int(base_now.timestamp() * 1000)
                inserir_timeline_event(db_path, paciente_id, ts_iso, ts_ms, "alert_close", descricao=None, meta={"inicio": inicio})
            except Exception:
                pass
        else:
            conn.execute(
                """
                UPDATE alertas
                SET status = :status
                WHERE paciente_id = :paciente_id AND inicio = :inicio
                """,
                {"status": status_destino, **params},
            )
            # timeline log for acknowledgement
            try:
                if str(status_destino).lower() == "reconhecido":
                    base_now = datetime.now().replace(microsecond=0)
                    ts_iso = base_now.strftime("%Y-%m-%dT%H:%M:%S")
                    ts_ms = int(base_now.timestamp() * 1000)
                    inserir_timeline_event(db_path, paciente_id, ts_iso, ts_ms, "alert_ack", descricao=None, meta={"inicio": inicio})
            except Exception:
                pass
        conn.commit()


def registrar_device(db_path: str, device_id: str, meta: dict | None = None) -> None:
    """Registra um device (ESP32) no banco, armazenando metadados opcionais."""
    if not device_id:
        raise ValueError("device_id deve ser informado.")
    meta_text = None if meta is None else json.dumps(meta, ensure_ascii=False)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO devices (device_id, meta) VALUES (?, ?)",
            (str(device_id), meta_text),
        )


def _to_ms(ts_iso: str | None, fallback_now: bool = True) -> int | None:
    if ts_iso is None:
        if not fallback_now:
            return None
        return int(pd.Timestamp.now().timestamp() * 1000)
    try:
        return int(pd.to_datetime(ts_iso).timestamp() * 1000)
    except Exception:
        if not fallback_now:
            return None
        return int(pd.Timestamp.now().timestamp() * 1000)


def resolver_paciente_por_device_em(db_path: str, device_id: str, ts_ms: int) -> str | None:
    """Resolve qual paciente (se houver) estava associado ao device no instante `ts_ms`.

    Retorna o paciente_id ou None.
    """
    if not device_id:
        return None
    with _connect(db_path) as conn:
        cur = conn.execute(
            "SELECT paciente_id FROM device_assignments WHERE device_id = ? AND start_ms <= ? AND (end_ms IS NULL OR end_ms >= ?) ORDER BY start_ms DESC LIMIT 1",
            (device_id, int(ts_ms), int(ts_ms)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        pid = row["paciente_id"]
        return None if pid is None else str(pid)


def inserir_device_event(db_path: str, device_id: str, ts: str, ts_ms: int, payload: dict) -> int:
    """Armazena o payload bruto recebido de um device para posterior reconciliação.

    Retorna o id do registro inserido.
    """
    if not device_id:
        raise ValueError("device_id deve ser informado.")
    meta_text = json.dumps(payload, ensure_ascii=False)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO device_events (device_id, ts, ts_ms, payload) VALUES (?, ?, ?, ?)",
            (device_id, ts, int(ts_ms), meta_text),
        )
        return int(cursor.lastrowid)


def ensure_minimal_paciente_ficha(db_path: str, paciente_id: str, nome: str | None = None, perfil: str | None = None, cama_id: str | None = None) -> None:
    """Ensure a minimal paciente_fichas record exists for `paciente_id`.

    If the ficha is missing, inserts a minimal record with provided `nome` (or paciente_id),
    `perfil` (defaults to 'medio') and optional `cama_id`.
    This is intentionally conservative and will not override an existing ficha.
    """
    if not paciente_id:
        raise ValueError("paciente_id deve ser informado.")

    perfil_val = None if perfil is None else str(perfil).strip().lower()
    if perfil_val not in PERFIS_VALIDOS:
        perfil_val = 'medio'

    cama_norm = _normalize_cama_id(cama_id)
    nome_val = None if nome is None else str(nome).strip() or None

    with _connect(db_path) as conn:
        # ensure base pacientes table has the id
        _ensure_paciente(conn, paciente_id)
        cur = conn.execute("SELECT paciente_id FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,))
        if cur.fetchone() is not None:
            return
        agora_iso = _utc_now_iso()
        conn.execute(
            "INSERT INTO paciente_fichas (paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (paciente_id, nome_val or paciente_id, perfil_val, cama_norm, None, agora_iso, agora_iso),
        )
        # If cama was provided, also create initial paciente_cama_history entry
        if cama_norm is not None:
            try:
                start_ms = int(pd.to_datetime(agora_iso).timestamp() * 1000)
                conn.execute(
                    "INSERT INTO paciente_cama_history (paciente_id, cama_id, start_ts, start_ms) VALUES (?, ?, ?, ?)",
                    (paciente_id, cama_norm, agora_iso, start_ms),
                )
            except Exception:
                pass
        conn.commit()


def listar_device_events(db_path: str, device_id: str | None = None, limit: int = 100, include_processed: bool = False) -> list[dict]:
    """List device_events. By default only returns events where processed_at IS NULL.

    Set include_processed=True to return all events regardless of processed_at.
    """
    sql = "SELECT id, device_id, ts, ts_ms, payload, created_at, processed_at FROM device_events"
    params: list = []
    where_clauses: list[str] = []
    if device_id:
        where_clauses.append("device_id = ?")
        params.append(device_id)
    if not include_processed:
        where_clauses.append("processed_at IS NULL")
    if where_clauses:
        sql = f"{sql} WHERE {' AND '.join(where_clauses)}"
    sql = f"{sql} ORDER BY ts_ms DESC LIMIT ?"
    params.append(int(limit))
    with _connect(db_path) as conn:
        cur = conn.execute(sql, tuple(params))
        rows = cur.fetchall()
    results: list[dict] = []
    for row in rows:
        try:
            payload_parsed = json.loads(row["payload"])
        except Exception:
            payload_parsed = None
        results.append({
            "id": row["id"],
            "device_id": row["device_id"],
            "ts": row["ts"],
            "ts_ms": int(row["ts_ms"]),
            "payload": payload_parsed,
            "created_at": row["created_at"],
            "processed_at": row["processed_at"],
        })
    return results


def listar_devices(db_path: str) -> list[dict]:
    with _connect(db_path) as conn:
        cur = conn.execute("SELECT device_id, meta, created_at FROM devices ORDER BY created_at DESC")
        rows = cur.fetchall()
    results: list[dict] = []
    for row in rows:
        try:
            meta_parsed = None if row["meta"] is None else json.loads(row["meta"])
        except Exception:
            meta_parsed = None
        results.append({
            "device_id": row["device_id"],
            "meta": meta_parsed,
            "created_at": row["created_at"],
        })
    return results


def delete_device_event(db_path: str, event_id: int, processed_at: str | None = None) -> int:
    """Mark a device_events row as processed (set processed_at). Returns number of rows updated.

    This preserves the payload for auditability. If `processed_at` is None, current UTC timestamp is used.
    """
    if processed_at is None:
        processed_at = _utc_now_iso()
    with _connect(db_path) as conn:
        cur = conn.execute("UPDATE device_events SET processed_at = ? WHERE id = ? AND processed_at IS NULL", (processed_at, int(event_id)))
        return cur.rowcount


def remover_paciente(db_path: str, paciente_id: str) -> int:
    """Remove a patient and all related records from the DB.

    Returns the number of rows removed from `paciente_fichas` (0 if not found, 1 if removed).
    This helper centralizes cleanup logic instead of issuing ad-hoc DELETEs elsewhere.
    """
    if not paciente_id:
        raise ValueError("paciente_id deve ser informado")
    with _connect(db_path) as conn:
        cur = conn.execute("SELECT paciente_id FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,))
        if cur.fetchone() is None:
            return 0
        # delete dependent records first to respect foreign keys and avoid orphans
        conn.execute("DELETE FROM paciente_rotinas WHERE paciente_id = ?", (paciente_id,))
        conn.execute("DELETE FROM paciente_documentos WHERE paciente_id = ?", (paciente_id,))
        conn.execute("DELETE FROM paciente_cama_history WHERE paciente_id = ?", (paciente_id,))
        conn.execute("DELETE FROM device_assignments WHERE paciente_id = ?", (paciente_id,))
        conn.execute("DELETE FROM timeline_events WHERE paciente_id = ?", (paciente_id,))
        # remove ficha and base pacientes row
        conn.execute("DELETE FROM paciente_fichas WHERE paciente_id = ?", (paciente_id,))
        conn.execute("DELETE FROM pacientes WHERE id = ?", (paciente_id,))
        conn.commit()
    return 1
