-- Quem e responsavel por qual paciente.
--
-- O dashboard de uma ala de 30 leitos e uma tabela de 30 linhas ordenada por
-- gravidade. A ordenacao esta certa, e o problema nao e ela: e que a lista e de
-- TODO MUNDO, logo de NINGUEM. Cada enfermeira le as trinta, decide quais sao
-- suas, e faz isso a cada atualizacao da tela.
--
-- Numa passagem de plantao isso e pior: quem entrou nao sabe quais leitos
-- assumiu, e a lista nao ajuda a descobrir.
--
-- TABELA E NAO COLUNA em `paciente_fichas`, por duas razoes:
--
--   * a atribuicao MUDA a cada turno, e uma coluna guardaria so a atual. Sem
--     historico nao da para responder "quem era o responsavel quando este
--     alerta ficou 4h aberto?", que e a pergunta que a analise de adesao por
--     enfermeiro (5.1) precisa fazer;
--
--   * um paciente pode ter mais de um responsavel numa transicao de plantao —
--     e legitimo que os dois vejam o leito por alguns minutos.
--
-- `liberado_em NULL` = atribuicao ativa. Mesmo padrao de `internacoes.alta_ms`:
-- encerrar e estado, nao delete, porque apagar destroi a evidencia de quem
-- respondia por aquele leito.

CREATE TABLE IF NOT EXISTS atribuicoes_paciente (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id   TEXT    NOT NULL,
    usuario       TEXT    NOT NULL,
    atribuido_em  TEXT    NOT NULL,
    atribuido_ms  INTEGER NOT NULL,
    -- Quem atribuiu. Auto-atribuicao ("assumir este leito") e o caso comum, e
    -- ali `atribuido_por` = `usuario`; a coordenacao distribuindo os leitos no
    -- inicio do plantao e o outro caso, e ali sao diferentes. Sem a coluna, os
    -- dois ficam indistinguiveis no historico.
    atribuido_por TEXT    NOT NULL,
    liberado_em   TEXT,
    liberado_ms   INTEGER,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario) REFERENCES users(username) ON DELETE CASCADE
);

-- A consulta quente e "quais pacientes sao meus AGORA", disparada a cada
-- carregamento do dashboard com o filtro ligado.
CREATE INDEX IF NOT EXISTS idx_atribuicoes_ativas
    ON atribuicoes_paciente (usuario, liberado_ms);

-- E a inversa, para a tela do paciente mostrar quem responde por ele.
CREATE INDEX IF NOT EXISTS idx_atribuicoes_paciente
    ON atribuicoes_paciente (paciente_id, liberado_ms);

-- O MESMO usuario nao pode assumir o mesmo paciente duas vezes sem ter
-- liberado. Sem isto, tocar duas vezes em "assumir" — o que acontece quando a
-- tela demora — criaria duas atribuicoes ativas, e a contagem de "meus
-- pacientes" passaria a mentir.
CREATE UNIQUE INDEX IF NOT EXISTS idx_atribuicao_unica_ativa
    ON atribuicoes_paciente (paciente_id, usuario)
    WHERE liberado_ms IS NULL;
