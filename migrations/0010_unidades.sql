-- Unidade (ala/setor): o sistema nao tinha nenhum conceito organizacional.
--
-- Um grep por unidade/ala/setor/enfermaria/turno/equipe em interface/,
-- migrations/, nucleo/ e frontend/src so achava prosa em comentario. O que
-- existia era `cama_id`, texto livre, UNICO EM TODA A INSTALACAO.
--
-- O que quebra com duas alas — tudo verificado no codigo, nao suposto:
--
--   * COLISAO DE LEITO NO BANCO. As duas alas tem um "Leito 12".
--     `_assert_cama_disponivel` recusa a segunda admissao citando um paciente
--     de outro predio: "Cama '12' ja esta atribuida ao paciente PAC-0007".
--   * ALARME CRUZADO. `useCriticalAlerts` dispara beep e notificacao para todo
--     alerta de alto risco DA INSTALACAO. A ala B acorda a enfermeira da ala A
--     — que e exatamente o mecanismo que treina a equipe a desligar
--     notificacao, e a partir dai o sistema inteiro perde a funcao.
--   * ORCAMENTO DE PAGINA COMPARTILHADO. `listar_alertas_frontend` traz
--     `limit=100` para o hospital todo; a ala mais movimentada consome a
--     pagina, e o banner de truncamento nao tem como dizer QUAL ala foi
--     cortada.
--   * `/stats` MEDIA AS DUAS ALAS num `completionRate` so, que e pior que nao
--     ter numero nenhum para efeito de accountability.
--   * ACESSO UNIVERSAL A PHI. Toda enfermeira do predio le o dado clinico de
--     todo paciente. A trilha de auditoria registra isso fielmente — o que a
--     transforma de defesa em prova.
--
-- A unidade mora em DOIS lugares, de proposito:
--   * `paciente_fichas.unidade_id` — onde o paciente esta AGORA. E o que
--     escopa listagem, alerta, estatistica e a unicidade do leito.
--   * `internacoes.unidade_id` — a qual unidade o EPISODIO pertenceu. Sobrevive
--     a alta, e e o que permite relatorio historico por ala depois que o
--     paciente saiu e a ficha ja nao diz mais nada.

CREATE TABLE IF NOT EXISTS unidades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    descricao TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Quais unidades cada usuario enxerga. N:N porque plantonista cobre mais de
-- uma ala, e coordenador cobre varias.
CREATE TABLE IF NOT EXISTS usuario_unidade (
    username TEXT NOT NULL,
    unidade_id INTEGER NOT NULL,
    PRIMARY KEY (username, unidade_id),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
    FOREIGN KEY (unidade_id) REFERENCES unidades(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_usuario_unidade_username ON usuario_unidade (username);

ALTER TABLE paciente_fichas ADD COLUMN unidade_id INTEGER REFERENCES unidades(id);
ALTER TABLE internacoes ADD COLUMN unidade_id INTEGER REFERENCES unidades(id);

-- Unidade padrao: tudo que ja existe passa a pertencer a ela, e todo usuario
-- que ja existe enxerga ela. O objetivo do backfill e que o comportamento da
-- instalacao atual NAO mude — quem roda uma ala so nao deve notar diferenca
-- nenhuma. Escopo que muda o que a equipe ve, sem ninguem pedir, seria pior que
-- nao ter escopo.
INSERT OR IGNORE INTO unidades (id, nome, descricao)
VALUES (1, 'Unidade Principal', 'Criada na migracao para unidades: recebe todos os dados anteriores.');

UPDATE paciente_fichas SET unidade_id = 1 WHERE unidade_id IS NULL;
UPDATE internacoes SET unidade_id = 1 WHERE unidade_id IS NULL;

INSERT OR IGNORE INTO usuario_unidade (username, unidade_id)
SELECT username, 1 FROM users;

-- Unicidade do leito passa a ser POR UNIDADE.
--
-- O indice antigo era global, e e ele que produz a colisao de "Leito 12". Cai
-- aqui; o novo permite o mesmo nome de leito em alas diferentes e continua
-- garantindo um paciente por leito dentro da ala.
DROP INDEX IF EXISTS idx_pac_fichas_cama;
CREATE UNIQUE INDEX IF NOT EXISTS idx_pac_fichas_unidade_cama
    ON paciente_fichas (unidade_id, cama_id) WHERE cama_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pac_fichas_unidade ON paciente_fichas (unidade_id);
CREATE INDEX IF NOT EXISTS idx_internacoes_unidade ON internacoes (unidade_id, admissao_ms DESC);
