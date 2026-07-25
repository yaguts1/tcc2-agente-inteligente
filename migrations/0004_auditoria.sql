-- Trilha de auditoria de acesso a dados de paciente.
--
-- Dado de saúde é dado pessoal SENSÍVEL na LGPD (Art. 5º, II). O que a lei
-- cobra e que este registro viabiliza:
--
--   * Art. 37 — o controlador mantém registro das operações de tratamento;
--   * Art. 46 — medidas de segurança e rastreabilidade do acesso;
--   * Art. 48 — comunicar incidente exige saber QUAIS titulares foram
--     expostos, o que só é possível se as LEITURAS também forem registradas.
--
-- Por isso a trilha cobre leitura, e não só escrita: em dado clínico, "quem
-- consultou o prontuário deste paciente" é a pergunta central. Também registra
-- tentativas NEGADAS (401/403), que são o sinal de uso indevido.

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- UTC naive, mesma convenção do resto do banco (ver interface/tempo.py).
    ts TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    usuario TEXT,               -- NULL em acesso anônimo/negado antes de autenticar
    papel TEXT,
    acao TEXT NOT NULL,         -- ex.: "GET /api/pacientes/{id}"
    metodo TEXT NOT NULL,
    rota TEXT NOT NULL,
    paciente_id TEXT,           -- titular do dado, quando identificável
    status INTEGER NOT NULL,    -- código HTTP da resposta
    negado INTEGER NOT NULL DEFAULT 0,
    ip TEXT,
    duracao_ms INTEGER,
    detalhe TEXT                -- JSON com contexto adicional
);

-- "Quem acessou o paciente X?" é a consulta que a LGPD exige responder.
CREATE INDEX IF NOT EXISTS idx_auditoria_paciente ON auditoria (paciente_id, ts_ms);
-- "O que o usuário Y fez?" — investigação de uso indevido.
CREATE INDEX IF NOT EXISTS idx_auditoria_usuario ON auditoria (usuario, ts_ms);
CREATE INDEX IF NOT EXISTS idx_auditoria_ts ON auditoria (ts_ms);
-- Varredura de tentativas negadas.
CREATE INDEX IF NOT EXISTS idx_auditoria_negado ON auditoria (negado, ts_ms);
