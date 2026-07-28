-- A qual ala pertencia cada periodo de leito.
--
-- `paciente_cama_history` guarda [inicio, fim) de cada leito que o paciente
-- ocupou, e e o que responde "de quem era esta leitura de sensor" na
-- reconciliacao. Faltava a unidade.
--
-- Sem ela, transferencia entre alas nao tem como ser registrada corretamente e,
-- pior, "quanto tempo de paciente esta ala teve" fica incalculavel: a unica
-- unidade gravada seria a ATUAL da ficha, entao um paciente que passou tres
-- dias na ala A e um na ala B apareceria como quatro dias na ala B.
--
-- Com esta coluna, cada pergunta tem UMA fonte:
--
--   onde o paciente esta agora     -> paciente_fichas.unidade_id
--   em que ala o episodio comecou  -> internacoes.unidade_id
--   paciente-hora por ala          -> paciente_cama_history, somando periodos
--
-- Em especial, `internacoes.unidade_id` NAO e sobrescrito numa transferencia:
-- ele registra onde a internacao COMECOU. Sobrescrever atribuiria a estadia
-- inteira a ultima ala, que e exatamente o erro que esta coluna evita.

ALTER TABLE paciente_cama_history ADD COLUMN unidade_id INTEGER REFERENCES unidades(id);

-- Backfill: os periodos existentes sao todos anteriores a existencia de mais de
-- uma ala, entao a unidade da ficha e a resposta certa — nao uma aproximacao.
-- Periodos de paciente sem ficha (dado orfao) ficam NULL, que e honesto:
-- ninguem sabe a que ala pertenceram.
UPDATE paciente_cama_history
   SET unidade_id = (
       SELECT f.unidade_id FROM paciente_fichas f
        WHERE f.paciente_id = paciente_cama_history.paciente_id
   )
 WHERE unidade_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_cama_history_unidade
    ON paciente_cama_history (unidade_id, start_ms DESC);
