-- Revogação de sessão e contas desativáveis.
--
-- Até aqui o logout apenas apagava os cookies: o JWT continuava válido pelas
-- 8h inteiras. Na prática não havia como tirar o acesso de ninguém — nem ao
-- desligar um funcionário, nem depois de uma senha vazar.
--
-- Três mecanismos, cada um para um caso:
--
--  * `tokens_revogados`      — encerra UMA sessão (logout naquele dispositivo).
--  * `users.tokens_validos_apos` — corte por data: invalida TODAS as sessões
--    anteriores ao instante gravado. Usado ao trocar senha ou ao forçar saída,
--    sem precisar enumerar os tokens emitidos.
--  * `users.ativo`           — desliga a conta; nenhum token dela é aceito e
--    o login passa a falhar. Preferido a apagar o usuário, que levaria junto a
--    autoria registrada na timeline (quem reconheceu/concluiu cada alerta).

ALTER TABLE users ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN tokens_validos_apos TEXT;

CREATE TABLE IF NOT EXISTS tokens_revogados (
    jti TEXT PRIMARY KEY,
    username TEXT,
    revogado_em TEXT NOT NULL DEFAULT (datetime('now')),
    -- Quando o próprio token expira. Depois disso a linha não serve para nada
    -- e pode ser removida — sem essa limpeza a tabela cresceria para sempre.
    expira_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tokens_revogados_expira ON tokens_revogados (expira_em);
