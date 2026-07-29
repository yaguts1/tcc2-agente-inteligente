-- ONDE a carga se acumulou, e a pressao que o sensor mediu.
--
-- 1. `alertas.sitio`
--
-- O motor passou a acumular carga por SITIO ANATOMICO (ver nucleo/posturas.py):
-- supino carrega sacro e calcaneos, lateral a 90° carrega o trocanter, lateral
-- a 30° quase nenhum dos criticos. O alerta agora sabe qual sitio estourou a
-- janela, e essa informacao muda a acao: "vire o paciente" e menos util que
-- "o trocanter direito esta sob carga ha 60 min", porque a segunda diz PARA QUAL
-- LADO virar.
--
-- Fica NULL nos alertas antigos, e nao ha o que inferir: eles foram abertos por
-- um motor que nao distinguia sitio.
--
-- 2. `grade.pressao_pico`
--
-- O campo era DECLARADO em `interface/schemas.py` desde sempre, atravessava
-- `ferramentas/exportador_jsonl.py` e NUNCA era gravado em lugar nenhum. Um
-- dado que o firmware ja envia e que o sistema jogava fora a cada amostra.
--
-- Importa porque e o unico sinal capaz de distinguir "o rotulo de postura
-- mudou" de "a carga sobre o sacro foi de fato aliviada" — a diferenca entre
-- reposicionamento efetivo e reposicionamento aparente, que hoje o sistema nao
-- consegue ver. Guardar agora e o que permite usar depois; sem a coluna, cada
-- amostra que passa e um dado perdido para sempre.

ALTER TABLE alertas ADD COLUMN sitio TEXT;
ALTER TABLE grade ADD COLUMN pressao_pico REAL;

-- Consulta "quais sitios mais disparam alerta nesta ala", que e o que orienta
-- onde reforcar o protocolo (coxim de calcaneo, mudanca de superficie).
CREATE INDEX IF NOT EXISTS idx_alertas_sitio ON alertas (sitio, inicio DESC);
