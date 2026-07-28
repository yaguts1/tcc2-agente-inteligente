-- Internacao (episodio): o substantivo que faltava no dominio.
--
-- Ate aqui existia CRUD de ficha e nada mais. As consequencias nao eram
-- cosmeticas:
--
--   * DAR ALTA ERA `delete()`, que apaga — nas palavras do proprio docstring —
--     "TODO o rastro clinico": alertas, grade, eventos, timeline e historico de
--     leito. A unica forma de tirar um paciente da tela destruia exatamente a
--     evidencia que acreditacao (ONA/JCI) e LGPD Art. 37 exigem guardar.
--   * Nao havia data de admissao, de alta, motivo, nem tempo de permanencia —
--     logo, nenhum denominador possivel para "paciente-hora monitorada", que e
--     o que falta para qualquer taxa de adesao significar alguma coisa.
--   * MUDANCA DE LEITO era efeito colateral de editar um campo de formulario,
--     sem operacao propria, sem atomicidade e sem registro do porque.
--
-- `alta` passa a ser ESTADO. `delete()` continua existindo para erro de
-- cadastro (paciente criado errado, duplicado), que e coisa diferente de alta.
--
-- Uma internacao ABERTA por paciente, garantido por indice unico parcial — o
-- mesmo recurso que `idx_pac_fichas_cama` ja usa para "um paciente por leito".
-- Sem isso, duas admissoes seguidas sem alta criariam dois episodios abertos e
-- nenhuma consulta saberia qual e o corrente.
--
-- `unidade_id` NAO entra aqui: e o proximo passo do plano (1.2), e e nesta
-- tabela que ele vai morar. Fica registrado para quem chegar antes.

CREATE TABLE IF NOT EXISTS internacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id TEXT NOT NULL,
    admissao_ts TEXT NOT NULL,
    admissao_ms INTEGER NOT NULL,
    alta_ts TEXT,
    alta_ms INTEGER,
    motivo_alta TEXT,
    admitido_por TEXT,
    dado_alta_por TEXT,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE
);

-- Uma internacao aberta por paciente.
CREATE UNIQUE INDEX IF NOT EXISTS idx_internacao_aberta
    ON internacoes (paciente_id) WHERE alta_ms IS NULL;

-- Consultas de permanencia e de "quem esta internado agora".
CREATE INDEX IF NOT EXISTS idx_internacoes_paciente_admissao
    ON internacoes (paciente_id, admissao_ms DESC);
CREATE INDEX IF NOT EXISTS idx_internacoes_alta
    ON internacoes (alta_ms);

-- Backfill: todo paciente com ficha esta, por definicao, internado — nao havia
-- outra forma de existir no sistema.
--
-- `admissao_ts` vem de `paciente_fichas.created_at`, que e o instante mais
-- proximo da admissao que o banco tem. NAO e a admissao real, e nada aqui pode
-- fingir que e: e quando o cadastro foi feito. Para os episodios que ja
-- rodaram, e o melhor disponivel; para os proximos, passa a ser registrado de
-- verdade. Mesma postura do `origem_fechamento` NULL em 0007 — dado honesto e
-- aproximado, nunca dado inventado com cara de exato.
--
-- `admitido_por` fica NULL de proposito: ninguem sabe quem admitiu.
INSERT INTO internacoes (paciente_id, admissao_ts, admissao_ms, admitido_por)
SELECT
    f.paciente_id,
    f.created_at,
    CAST(strftime('%s', f.created_at) AS INTEGER) * 1000,
    NULL
FROM paciente_fichas f
WHERE f.created_at IS NOT NULL
  AND strftime('%s', f.created_at) IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM internacoes i WHERE i.paciente_id = f.paciente_id);
