-- Traz `agendas_paciente` para dentro do schema versionado e corrige a FK.
--
-- Dois problemas, um consequencia do outro:
--
-- 1. A tabela era criada por DDL ad-hoc no IMPORT de interface/endpoints_agenda.py
--    (via dao_agenda.ensure_agendas_table), fora do runner. Consequencia:
--    `schema_version` nunca descreveu o schema real, e uma tabela que guarda
--    configuracao clinica (quando NAO alertar) ficava invisivel para qualquer
--    um lendo migrations/ para saber o que existe no banco.
--
-- 2. A FK apontava para `fichas_paciente(paciente_id)` — tabela que nunca
--    existiu; a real e `paciente_fichas`. O erro nunca apareceu porque no SQLite
--    as foreign keys vem DESLIGADAS por conexao, entao a declaracao era
--    decoracao. Ao ligar `PRAGMA foreign_keys=ON` (interface/db_core.py) ela
--    passa a ser avaliada, e todo INSERT de agenda quebraria com "no such table".
--
-- A referencia correta e `pacientes(id)`, nao `paciente_fichas`: quem cria
-- agenda chama `_ensure_paciente`, que garante a linha em `pacientes` — e nada
-- no fluxo garante que exista ficha. Referenciar a ficha recusaria agendas
-- legitimas.
--
-- Recriar e preciso: o SQLite nao permite alterar constraint por ALTER TABLE.
-- Bancos novos caem no CREATE e saem daqui; bancos existentes passam pelo
-- copia-e-troca abaixo, preservando os ids (a tela referencia agenda por id).

-- Forma ANTIGA, só para o copia-e-troca abaixo achar a tabela num banco que
-- nunca a teve (ordem de import vs. migration nao e garantida, e uma migration
-- que depende dessa ordem quebra no dia em que ela mudar).
CREATE TABLE IF NOT EXISTS agendas_paciente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    descricao TEXT,
    dias_semana TEXT,
    hora_inicio TEXT,
    hora_fim TEXT,
    data_inicio TEXT,
    data_fim TEXT,
    modo TEXT DEFAULT 'suprimir',
    reducao_janela_min INTEGER,
    ativo BOOLEAN DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agendas_paciente_nova (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    descricao TEXT,
    dias_semana TEXT,
    hora_inicio TEXT,
    hora_fim TEXT,
    data_inicio TEXT,
    data_fim TEXT,
    modo TEXT DEFAULT 'suprimir',
    reducao_janela_min INTEGER,
    ativo BOOLEAN DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
);

-- Só copia se a tabela antiga existir. Um banco novo tem a nova vazia e segue.
INSERT INTO agendas_paciente_nova (
    id, paciente_id, tipo, descricao, dias_semana, hora_inicio, hora_fim,
    data_inicio, data_fim, modo, reducao_janela_min, ativo, created_at, updated_at
)
SELECT
    a.id, a.paciente_id, a.tipo, a.descricao, a.dias_semana, a.hora_inicio, a.hora_fim,
    a.data_inicio, a.data_fim, a.modo, a.reducao_janela_min, a.ativo, a.created_at, a.updated_at
FROM agendas_paciente a
-- Agenda cujo paciente ja nao existe violaria a FK nova e abortaria a migration
-- inteira. Descartar e o comportamento certo: e configuracao orfa de um paciente
-- removido, que a tela nunca mostrou e nenhum alerta jamais consultaria.
WHERE EXISTS (SELECT 1 FROM pacientes p WHERE p.id = a.paciente_id);

DROP TABLE IF EXISTS agendas_paciente;

ALTER TABLE agendas_paciente_nova RENAME TO agendas_paciente;

CREATE INDEX IF NOT EXISTS idx_agendas_paciente_id ON agendas_paciente(paciente_id);
CREATE INDEX IF NOT EXISTS idx_agendas_ativo ON agendas_paciente(ativo);
