-- Lesao por pressao: a variavel de DESFECHO, que nao existia.
--
-- O sistema media adesao ao reposicionamento e nunca registrava se a lesao
-- aconteceu. Sem isso, a correlacao que o projeto existe para demonstrar —
-- adesao ao protocolo vs. incidencia de LPP — nao e computavel NEM EM
-- PRINCIPIO a partir do banco. Media-se o processo e ignorava-se o resultado.
--
-- Tres decisoes de modelagem que mudam o que se consegue afirmar:
--
-- 1. `origem` DISTINGUE O QUE E INCIDENCIA DO QUE NAO E.
--
-- Uma lesao que o paciente TROUXE nao e falha do cuidado desta unidade — e
-- prevalencia na admissao. Uma que APARECEU aqui e incidencia, e e a unica que
-- pode ser atribuida ao cuidado prestado. Somar as duas produz um numero que
-- pune a unidade que recebe paciente grave de outro servico, e e exatamente o
-- numero que faz uma equipe deixar de registrar lesao.
--
-- Por isso `origem` e NOT NULL, sem default: quem registra a lesao PRECISA
-- responder essa pergunta, e um default silencioso decidiria por ela.
--
-- 2. A EVOLUCAO FICA EM TABELA PROPRIA.
--
-- Uma lesao muda de estagio ao longo do tempo, e a trajetoria E o dado clinico
-- — "estagio 2 que cicatrizou em 6 dias" e "estagio 2 que virou 4" nao sao o
-- mesmo desfecho. Guardar so o estagio atual apagaria a diferenca a cada
-- reavaliacao; guardar so o inicial esconderia a piora.
--
-- O estagio atual e DERIVADO da avaliacao mais recente, e nao duplicado numa
-- coluna: duas fontes para o mesmo fato divergem, e aqui a que divergiria e a
-- que alimenta o indicador.
--
-- 3. `internacao_id` AMARRA A LESAO AO EPISODIO.
--
-- Sem ele, uma lesao de uma internacao anterior contaria na atual, e o
-- denominador (paciente-dia daquele episodio) nao casaria com o numerador.
--
-- Vocabulario de estagio: classificacao NPUAP/EPUAP 2016, que e a adotada no
-- Brasil como "Lesao por Pressao" (a traducao oficial trocou "ulcera" por
-- "lesao" justamente porque estagio 1 nao tem ulceracao).

CREATE TABLE IF NOT EXISTS lesoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id TEXT NOT NULL,
    internacao_id INTEGER,
    unidade_id INTEGER,

    -- Sitio anatomico. Texto com CHECK em vez de tabela propria: a lista e
    -- fechada, curta e estavel, e uma tabela de dominio aqui so adicionaria um
    -- JOIN a toda consulta.
    sitio TEXT NOT NULL,

    -- `presente_na_admissao` | `adquirida`. Ver decisao 1 acima.
    origem TEXT NOT NULL,

    identificada_ts TEXT NOT NULL,
    identificada_ms INTEGER NOT NULL,
    identificada_por TEXT,

    -- Desfecho da lesao. NULL enquanto aberta.
    fechada_ts TEXT,
    fechada_ms INTEGER,
    -- `cicatrizada` | `alta_com_lesao` | `obito` | `erro_de_registro`
    desfecho TEXT,

    observacoes TEXT,

    FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
    FOREIGN KEY (internacao_id) REFERENCES internacoes(id),
    FOREIGN KEY (unidade_id) REFERENCES unidades(id),

    CHECK (origem IN ('presente_na_admissao', 'adquirida')),
    CHECK (sitio IN (
        'sacro', 'coccige', 'isquio_esquerdo', 'isquio_direito',
        'trocanter_esquerdo', 'trocanter_direito',
        'calcaneo_esquerdo', 'calcaneo_direito',
        'maleolo_esquerdo', 'maleolo_direito',
        'occipital', 'escapula_esquerda', 'escapula_direita',
        'orelha_esquerda', 'orelha_direita',
        'cotovelo_esquerdo', 'cotovelo_direito',
        'nariz', 'outro'
    )),
    CHECK (desfecho IS NULL OR desfecho IN (
        'cicatrizada', 'alta_com_lesao', 'obito', 'erro_de_registro'
    ))
);

-- Uma avaliacao de estagio, num instante. A PRIMEIRA e registrada junto com a
-- lesao; as seguintes sao a evolucao.
CREATE TABLE IF NOT EXISTS lesao_avaliacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesao_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    estagio TEXT NOT NULL,
    -- Medidas em cm, opcionais: nem todo servico mede, e exigir numero faria a
    -- equipe inventar um.
    comprimento_cm REAL,
    largura_cm REAL,
    avaliada_por TEXT,
    observacoes TEXT,

    FOREIGN KEY (lesao_id) REFERENCES lesoes(id) ON DELETE CASCADE,

    -- NPUAP/EPUAP 2016. `nao_classificavel` e `tissular_profunda` nao sao
    -- "nao sei": sao categorias clinicas definidas — a primeira quando a base
    -- esta coberta por esfacelo/escara e a profundidade nao pode ser avaliada,
    -- a segunda quando ha descoloracao intacta persistente.
    CHECK (estagio IN (
        'estagio_1', 'estagio_2', 'estagio_3', 'estagio_4',
        'nao_classificavel', 'tissular_profunda',
        'dispositivo_medico', 'membrana_mucosa'
    ))
);

CREATE INDEX IF NOT EXISTS idx_lesoes_paciente ON lesoes (paciente_id, identificada_ms DESC);
CREATE INDEX IF NOT EXISTS idx_lesoes_internacao ON lesoes (internacao_id);
-- O indice do INDICADOR: incidencia e "adquiridas, nesta unidade, nesta
-- janela".
CREATE INDEX IF NOT EXISTS idx_lesoes_indicador
    ON lesoes (unidade_id, origem, identificada_ms DESC);
CREATE INDEX IF NOT EXISTS idx_lesao_avaliacoes_lesao
    ON lesao_avaliacoes (lesao_id, ts_ms DESC);

-- Sem backfill: nao ha de onde tirar. Nenhuma lesao foi registrada porque nao
-- havia onde registrar, e inventar dado de desfecho seria pior que nao ter —
-- um estudo com numerador fabricado nao e um estudo.
