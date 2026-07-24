-- Schema baseline: todas as tabelas e indices do sistema, no estado atual
-- (equivalente ao que interface/db_core.py:criar_esquema() fazia antes de
-- existir um runner de migrations, ja incorporando as colunas que eram
-- adicionadas via ALTER TABLE ad-hoc: paciente_fichas.cama_id, grade.confianca,
-- users.role).

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
    confianca REAL,
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
CREATE INDEX IF NOT EXISTS idx_grade_paciente_ts ON grade (paciente_id, ts);
CREATE INDEX IF NOT EXISTS idx_alertas_status ON alertas (paciente_id, status);
CREATE INDEX IF NOT EXISTS idx_alertas_inicio ON alertas (inicio);
CREATE INDEX IF NOT EXISTS idx_alertas_paciente_inicio ON alertas (paciente_id, inicio);
CREATE INDEX IF NOT EXISTS idx_eventos_inicio ON eventos (inicio);

-- Indices compostos adicionais para queries frequentes
CREATE INDEX IF NOT EXISTS idx_alertas_status_inicio ON alertas (status, inicio DESC);
CREATE INDEX IF NOT EXISTS idx_alertas_paciente_status_inicio ON alertas (paciente_id, status, inicio DESC);
CREATE INDEX IF NOT EXISTS idx_grade_paciente_ts_desc ON grade (paciente_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_eventos_paciente_inicio ON eventos (paciente_id, inicio DESC);

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
    role TEXT DEFAULT 'staff',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at);
