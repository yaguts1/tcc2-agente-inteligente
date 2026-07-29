-- Quem respondeu, quando, e por que fechou.
--
-- A migration 0007 registrou quem FECHOU o alerta e por qual caminho. Faltavam
-- as outras duas perguntas que uma coordenacao faz sobre a operacao.
--
-- 1. QUEM RECONHECEU, E EM QUANTO TEMPO.
--
-- O ator do reconhecimento so existia como frase em portugues dentro de
-- `timeline_events.descricao` ("Alerta reconhecido por fulano") e como chave
-- solta no `meta` JSON. Consequencias: nao da para agregar por enfermeiro, nao
-- da para filtrar, e qualquer consulta precisaria fazer LIKE em prosa.
--
-- Pior, e o motivo principal desta coluna: TEMPO ATE RECONHECIMENTO nao era
-- derivavel do modelo. `duracao_min` e `fim - inicio`, ou seja
-- deteccao -> resolucao. O intervalo que diz se a ala e RESPONSIVA —
-- deteccao -> alguem viu — nao estava em lugar nenhum consultavel.
--
-- 2. POR QUE O ALERTA FOI FECHADO.
--
-- Concluir nao recebia justificativa nenhuma: o dialogo era sim/nao. Entao
-- "reposicionei o paciente", "estava em cirurgia", "o paciente recusou",
-- "contraindicado por retalho na regiao sacral" e "falso alarme, o sensor
-- deslocou" viravam exatamente a mesma linha.
--
-- Cada um desses e um fato clinico diferente e pede uma acao diferente. E, sem
-- separar o falso alarme dos demais, A TAXA DE FALSO-POSITIVO E ESTRUTURALMENTE
-- INCOGNOSCIVEL — logo, inmelhoravel. Fadiga de alarme e a razao dominante pela
-- qual sistemas de alerta clinico sao abandonados, e ela comeca exatamente
-- aqui: num alerta que erra sem que ninguem consiga medir quanto.
--
-- 3. IDENTIFICACAO PROFISSIONAL.
--
-- COFEN Res. 429/2012 exige que o registro de enfermagem identifique o
-- profissional por nome E numero de registro no conselho. Com um `username`
-- solto, o que este sistema produz e apoio de plantao — nao documentacao — e a
-- equipe segue registrando reposicionamento a parte no prontuario, que e o
-- caminho mais curto para a ferramenta ser abandonada.

ALTER TABLE alertas ADD COLUMN reconhecido_por TEXT;
ALTER TABLE alertas ADD COLUMN reconhecido_em TEXT;
ALTER TABLE alertas ADD COLUMN motivo_fechamento TEXT;

-- Consulta de tempo-de-resposta por janela.
CREATE INDEX IF NOT EXISTS idx_alertas_reconhecido_em ON alertas (reconhecido_em);
CREATE INDEX IF NOT EXISTS idx_alertas_motivo ON alertas (motivo_fechamento);

ALTER TABLE users ADD COLUMN coren TEXT;
ALTER TABLE users ADD COLUMN categoria TEXT;

-- Sem backfill nas tres colunas de alerta, e o motivo e o mesmo de 0007: nao da
-- para saber retroativamente quem reconheceu cada alerta antigo nem por que ele
-- foi fechado. Extrair da prosa de `timeline_events` produziria um dado que
-- PARECE preciso e nao e — pior que o NULL honesto, porque ninguem depois
-- saberia distinguir o que foi lido de verdade do que foi inferido de um LIKE.
--
-- Quem quiser o historico antigo tem a timeline, que continua la, com a
-- ressalva de que e prosa.
