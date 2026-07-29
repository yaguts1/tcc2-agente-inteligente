-- Escala de Braden: o instrumento que a enfermagem ja usa.
--
-- O risco era um enum de tres valores num dropdown — `baixo`, `medio`, `alto` —
-- sem escore, sem subescores, sem data de reavaliacao e sem registro de quem
-- classificou. As janelas de reposicionamento (60/90/120 min) eram variaveis de
-- ambiente GLOBAIS, e nada no repositorio citava fonte para esses numeros.
--
-- Numa ala brasileira, BRADEN E O QUE VAI PARA O PRONTUARIO (Protocolo de
-- Prevencao de Lesao por Pressao, MS/ANVISA/FIOCRUZ 2013). Uma ferramenta que
-- nao o consome pede que a enfermeira mantenha uma SEGUNDA classificacao de
-- risco, paralela e sem justificativa, ao lado da que ela ja e obrigada a
-- registrar. Duas classificacoes divergem — e a que este sistema usava era a
-- que ninguem auditava.
--
-- Decisoes:
--
-- 1. UMA LINHA POR AVALIACAO, nunca UPDATE.
--
-- Braden e reavaliado a cada mudanca de condicao, e a TRAJETORIA do escore e
-- dado clinico: um paciente que entrou com 18 e esta com 11 esta piorando, e
-- isso nao aparece se cada avaliacao sobrescrever a anterior. Mesma razao da
-- tabela de avaliacoes de lesao (migrations/0014).
--
-- 2. OS SEIS SUBESCORES SAO COLUNAS, nao um JSON.
--
-- Sao seis campos fixos, definidos pelo instrumento, e cada um responde uma
-- pergunta diferente ("por que este paciente e de risco?" costuma se responder
-- com "mobilidade 1 e nutricao 1"). Num JSON, nenhum deles e consultavel sem
-- parse, e o total nao seria conferivel contra as partes.
--
-- 3. O TOTAL E COLUNA, apesar de ser soma das partes.
--
-- Aqui a duplicacao e deliberada, ao contrario do estagio da lesao: o total e o
-- que TODA consulta filtra e ordena, e recalcula-lo em SQL a cada leitura
-- espalharia a aritmetica do instrumento pelo banco. O CHECK abaixo garante que
-- ele nunca divirja das partes — que era a objecao real a duplicar.

CREATE TABLE IF NOT EXISTS braden_avaliacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id TEXT NOT NULL,
    internacao_id INTEGER,

    percepcao_sensorial INTEGER NOT NULL,
    umidade INTEGER NOT NULL,
    atividade INTEGER NOT NULL,
    mobilidade INTEGER NOT NULL,
    nutricao INTEGER NOT NULL,
    friccao_cisalhamento INTEGER NOT NULL,

    total INTEGER NOT NULL,
    -- Faixa ORIGINAL de Braden (cinco niveis), preservada mesmo que o perfil do
    -- sistema colapse as pontas em tres. Sem ela, a distincao entre "alto" e
    -- "muito alto" desapareceria do registro.
    faixa TEXT NOT NULL,
    -- Perfil derivado que passou a valer para o motor.
    perfil TEXT NOT NULL,

    avaliada_ts TEXT NOT NULL,
    avaliada_ms INTEGER NOT NULL,
    avaliada_por TEXT,
    observacoes TEXT,

    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    FOREIGN KEY (internacao_id) REFERENCES internacoes(id),

    -- Cinco subescalas vao de 1 a 4; friccao/cisalhamento vai de 1 a 3. Nao e
    -- detalhe de digitacao: aceitar 4 ali inflaria o total e poderia rebaixar o
    -- paciente de faixa de risco sem ninguem perceber.
    CHECK (percepcao_sensorial BETWEEN 1 AND 4),
    CHECK (umidade BETWEEN 1 AND 4),
    CHECK (atividade BETWEEN 1 AND 4),
    CHECK (mobilidade BETWEEN 1 AND 4),
    CHECK (nutricao BETWEEN 1 AND 4),
    CHECK (friccao_cisalhamento BETWEEN 1 AND 3),

    -- O total NUNCA divergir das partes. E o que torna seguro guardar os dois.
    CHECK (total = percepcao_sensorial + umidade + atividade + mobilidade
                 + nutricao + friccao_cisalhamento),

    CHECK (faixa IN ('sem_risco', 'baixo', 'moderado', 'alto', 'muito_alto')),
    CHECK (perfil IN ('baixo', 'medio', 'alto'))
);

CREATE INDEX IF NOT EXISTS idx_braden_paciente
    ON braden_avaliacoes (paciente_id, avaliada_ms DESC);
-- Consulta "quem esta com reavaliacao vencida", que e o alerta de processo.
CREATE INDEX IF NOT EXISTS idx_braden_avaliada_ms
    ON braden_avaliacoes (avaliada_ms DESC);

-- Sem backfill, e nao ha de onde tirar: o `perfil` que existe nas fichas foi
-- escolhido num dropdown, sem escore por tras. Fabricar subescores que somem
-- ate a faixa correspondente inventaria uma avaliacao clinica que ninguem fez —
-- e um Braden inventado no prontuario e pior que Braden nenhum.
--
-- O `perfil` da ficha continua sendo o que o motor le. A primeira avaliacao de
-- Braden de cada paciente passa a defini-lo.
