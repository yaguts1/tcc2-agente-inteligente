-- Encadeamento da trilha de auditoria.
--
-- Ate aqui a trilha vivia no MESMO SQLite que ela audita, sem nenhuma protecao:
-- um UPDATE apaga o registro de um acesso indevido, um DELETE apaga a linha
-- inteira, e nada no sistema fica diferente. Ou seja, a trilha era confiavel
-- exatamente ate o momento em que alguem tivesse motivo para adultera-la — que
-- e o unico momento em que ela precisa ser confiavel.
--
-- Cada entrada passa a carregar o hash da anterior, formando uma cadeia:
-- alterar um campo, apagar uma linha ou inserir uma no meio quebra o elo
-- seguinte e a verificacao aponta exatamente onde.
--
-- LIMITE, que precisa estar claro: isto torna a adulteracao DETECTAVEL, nao
-- impossivel. Quem tem acesso de escrita ao banco pode recalcular a cadeia
-- inteira depois de mexer. E por isso que o hash e um HMAC com chave
-- (UPP_AUDIT_KEY): sem a chave, que nao mora no banco, nao da para forjar elos
-- validos. A protecao real vem de a chave estar FORA do alcance de quem
-- administra o banco.
--
-- As linhas que ja existiam ficam com hash NULL. Nao sao recalculadas de
-- proposito: preencher a cadeia retroativamente produziria uma verificacao que
-- "aprova" registros que nunca estiveram protegidos — uma garantia falsa, que e
-- pior que a ausencia de garantia. Elas sao reportadas como NAO protegidas.

ALTER TABLE auditoria ADD COLUMN hash_anterior TEXT;
ALTER TABLE auditoria ADD COLUMN hash TEXT;

-- A verificacao percorre a cadeia em ordem de insercao.
CREATE INDEX IF NOT EXISTS idx_auditoria_cadeia ON auditoria (id, hash);
