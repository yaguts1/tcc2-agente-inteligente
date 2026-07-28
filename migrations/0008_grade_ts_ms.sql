-- Teto silencioso de UMA amostra por segundo na grade.
--
-- A chave primaria era `(paciente_id, ts)`, `ts` e texto ISO, e `norm_iso`
-- (interface/db_core.py) faz `.dt.floor("s")` — entao duas amostras do mesmo
-- segundo viravam a MESMA chave. Somado ao `INSERT OR IGNORE` de
-- `inserir_grade`, a segunda era descartada:
--
--   * sem erro, porque `OR IGNORE` e o comportamento pedido;
--   * sem log e sem metrica, porque ninguem olhava `total_changes` por linha;
--   * com resposta de SUCESSO para o dispositivo, que dava a amostra por
--     entregue e seguia em frente.
--
-- Na cadencia de hoje (o JSONL de exemplo usa `amostra_ms: 60000`) isso nao
-- descarta nada. O problema e que o teto e INVISIVEL: no dia em que a cadencia
-- subir para sub-segundo — que e exatamente o caminho para detectar micro
-- movimentos — metade das leituras evapora e nada no sistema indica.
--
-- Ja custou caro uma vez, de um jeito instrutivo: um teste escrito para provar
-- que o filtro de qualidade deduplicava retransmissoes do WebSocket passava com
-- e sem o filtro, porque era esta PK comendo a duplicata. Um teto que some com
-- dado tambem esconde bug em teste.
--
-- A chave passa a ser `(paciente_id, ts_ms)`, em milissegundos inteiros.
--
-- `ts` FICA, e continua em resolucao de segundo: e o que
-- `repositories/monitoramento.py`, os exports, os scripts de diagnostico e as
-- janelas por data leem hoje. Mexer nele junto transformaria uma correcao de
-- chave numa migracao de formato em cima de todo consumidor de grade.
--
-- Recriar e preciso: o SQLite nao permite trocar a PK por ALTER TABLE.

CREATE TABLE IF NOT EXISTS grade_nova (
    paciente_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    postura TEXT,
    confianca REAL,
    PRIMARY KEY (paciente_id, ts_ms)
);

-- Backfill: as linhas existentes sao todas de segundo cheio, entao
-- `ts_ms = epoch(ts) * 1000` e exato, nao uma aproximacao. `strftime('%s')`
-- interpreta o texto como UTC, que e o referencial em que a coluna e gravada
-- (ver interface/tempo.py).
--
-- Linhas com `ts` ilegivel dariam `ts_ms` NULL e violariam a PK, abortando a
-- migration inteira: ficam de fora. Sao amostras que nenhuma consulta por
-- tempo ja conseguia enxergar.
INSERT OR IGNORE INTO grade_nova (paciente_id, ts, ts_ms, postura, confianca)
SELECT paciente_id, ts, CAST(strftime('%s', ts) AS INTEGER) * 1000, postura, confianca
FROM grade
WHERE ts IS NOT NULL AND strftime('%s', ts) IS NOT NULL;

DROP TABLE IF EXISTS grade;

ALTER TABLE grade_nova RENAME TO grade;

CREATE INDEX IF NOT EXISTS idx_grade_paciente_ts ON grade (paciente_id, ts);
CREATE INDEX IF NOT EXISTS idx_grade_paciente_ts_desc ON grade (paciente_id, ts DESC);
-- Ordenacao determinista quando varias amostras caem no mesmo segundo: sem
-- isto, `ORDER BY ts` empata e a ordem entre elas fica a criterio do SQLite.
CREATE INDEX IF NOT EXISTS idx_grade_paciente_ts_ms ON grade (paciente_id, ts_ms DESC);
