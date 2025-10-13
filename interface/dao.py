"""Camada simples de persistencia SQLite para dados de simulacao e fichas de pacientes."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
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
            """
        )
        _ensure_cama_column(conn)
        conn.commit()


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
        cursor = conn.execute(
            "SELECT 1 FROM paciente_fichas WHERE paciente_id = ?",
            (paciente_id,),
        )
        if cursor.fetchone() is None:
            raise LookupError("Paciente nao encontrado.")
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

    registros = [
        (paciente_id, ts, postura)
        for ts, postura in zip(timestamps, posturas)
        if ts is not None
    ]

    if not registros:
        return 0

    with _connect(db_path) as conn:
        _ensure_paciente(conn, paciente_id)
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO grade (paciente_id, ts, postura) VALUES (?, ?, ?)",
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
        return conn.total_changes - before


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
    """ Busca alertas (qualquer status) com inicio >= agora - horas (se horas for None, traz todos), ordenados por inicio ASC. Retorna lista de dicts. """
    limite_inferior: str | None = None
    if horas is not None:
        agora = datetime.now().replace(microsecond=0)
        limite_inferior = (agora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")

    with _connect(db_path) as conn:
        if limite_inferior is None:
            cursor = conn.execute(
                "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
                "FROM alertas ORDER BY inicio ASC"
            )
        else:
            cursor = conn.execute(
                "SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min "
                "FROM alertas WHERE inicio >= ? ORDER BY inicio ASC",
                (limite_inferior,),
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
