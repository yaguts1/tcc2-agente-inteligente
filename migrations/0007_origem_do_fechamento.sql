-- Quem fechou o alerta: a equipe ou o proprio paciente?
--
-- Um alerta chega a 'fechado' por dois caminhos completamente diferentes:
--
--   1. a enfermagem virou o paciente e clicou "Reposicionar" na tela
--      (alterar_status_alerta, via services/alerts_service.py);
--   2. o motor detectou movimento espontaneo e fechou sozinho
--      (repositories/alertas.py:119-131, o UPSERT com `excluded.fim IS NOT NULL`).
--
-- Ate aqui os dois gravavam exatamente a mesma linha. Consequencia: um paciente
-- que rola sozinho na cama produzia um "concluido" sem nenhum humano envolvido,
-- e nao havia coluna em lugar nenhum que separasse os dois casos.
--
-- Isso contamina TUDO que se mede sobre a operacao:
--   * `completedToday` e `completionRate` (routers/dashboard.py:114,124) — a KPI
--     de capa do dashboard misturava adesao da enfermagem com mobilidade do
--     paciente;
--   * o export CSV/PDF (ferramentas/exportador.py), que mapeia fechado ->
--     completed e e o que vai para a coordenacao;
--   * qualquer analise de adesao do TCC, cuja variavel de desfecho primaria
--     passa a ser uma mistura de duas coisas nao comparaveis.
--
-- `origem_fechamento` responde "por qual caminho fechou" e `fechado_por` "quem
-- foi", quando ha um quem. Ficam NULL nas linhas antigas de proposito: nao da
-- para saber retroativamente qual caminho fechou cada alerta, e chutar
-- 'equipe' inventaria adesao que talvez nunca tenha existido. Um NULL honesto e
-- melhor que um numero bonito e falso — mesma escolha (e mesmo motivo) do hash
-- NULL nas linhas pre-existentes da auditoria, em 0005.
--
-- Valores de `origem_fechamento`:
--   'equipe'   — alguem clicou na tela; `fechado_por` traz o usuario
--   'sensor'   — o motor detectou movimento espontaneo; `fechado_por` e NULL
--   'sistema'  — fechamento automatico por regra (alta, transferencia, expurgo)

ALTER TABLE alertas ADD COLUMN fechado_por TEXT;
ALTER TABLE alertas ADD COLUMN origem_fechamento TEXT;

-- Consultas de adesao filtram por origem dentro de uma janela de tempo; sem
-- isto elas varrem a tabela inteira.
CREATE INDEX IF NOT EXISTS idx_alertas_origem_inicio
    ON alertas (origem_fechamento, inicio DESC);
