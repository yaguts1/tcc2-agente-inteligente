-- Inscricoes de Web Push.
--
-- A notificacao morria com a aba. `useCriticalAlerts` toca um beep WebAudio e
-- usa a Notification API — as duas exigem a aba viva, e o tratamento da
-- suspensao de autoplay do Chrome DESISTE EM SILENCIO quando o navegador
-- recusa. Engenharia correta, e clinicamente significa que o aviso pode nunca
-- soar sem que ninguem seja informado disso.
--
-- Com a escada de escalonamento (4.2) o buraco ficou maior: um alerta que
-- escala para `violacao` as 04:00 agora TEM o que avisar, e nao tinha por onde.
--
-- Uma linha por (usuario, aparelho). O mesmo usuario tem inscricao no tablet da
-- ala e no proprio celular, e as duas precisam receber.

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario       TEXT    NOT NULL,
    -- URL que o navegador do usuario deu ao servico de push do fabricante.
    -- E o identificador natural do aparelho: reinscricao no mesmo navegador
    -- devolve o mesmo endpoint, entao UNIQUE evita duplicar e mandar o aviso
    -- duas vezes para a mesma tela.
    endpoint      TEXT    NOT NULL UNIQUE,
    -- Chaves de criptografia da inscricao. O servidor NAO consegue ler o que
    -- manda sem elas, e o servico de push do fabricante nunca ve o conteudo —
    -- o que importa aqui, porque a mensagem carrega leito e nome de paciente.
    p256dh        TEXT    NOT NULL,
    auth          TEXT    NOT NULL,
    criado_em     TEXT    NOT NULL,
    -- Ultimo envio bem-sucedido e ultima falha. Servico de push devolve 404/410
    -- quando a inscricao morreu (app desinstalado, permissao revogada); sem
    -- registrar isso, a tabela so cresce e cada ciclo tenta entregar para
    -- aparelhos que nao existem mais.
    ultimo_envio  TEXT,
    ultima_falha  TEXT,
    falhas        INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (usuario) REFERENCES users(username) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_push_usuario ON push_subscriptions(usuario);

-- Qual foi o ultimo nivel de escalonamento JA NOTIFICADO para cada alerta.
--
-- Sem isto o envio seria por estado e nao por transicao, e o mesmo alerta
-- geraria uma notificacao a cada ciclo do loop de fundo — que e a maneira mais
-- rapida de fazer a equipe desligar as notificacoes do navegador, e uma vez
-- desligadas elas nao voltam.
--
-- A chave e (paciente_id, inicio), que e o mesmo par que forma o `alert_id`.
CREATE TABLE IF NOT EXISTS push_nivel_notificado (
    paciente_id   TEXT NOT NULL,
    inicio        TEXT NOT NULL,
    nivel         TEXT NOT NULL,
    notificado_em TEXT NOT NULL,
    PRIMARY KEY (paciente_id, inicio)
);
