-- Credencial por dispositivo, no lugar de um segredo unico para a frota.
--
-- `UPP_DEVICE_TOKEN` e uma variavel de ambiente com UM valor, gravado no
-- `config.h` de TODOS os ESP32. Consequencias:
--
--   * um ESP32 arrancado da parede (e sao aparelhos acessiveis, presos ao leito,
--     num predio com circulacao de publico) entrega a credencial da frota
--     inteira. Quem a tiver injeta postura em nome de qualquer leito;
--   * nao ha revogacao possivel abaixo de trocar o segredo e reflashear todos
--     os aparelhos — ou seja, na pratica, nao ha revogacao;
--   * nao da para saber QUAL aparelho enviou: o token nao distingue ninguem.
--
-- O token e guardado como SHA-256, nao em texto puro. Nao e bcrypt de
-- proposito: bcrypt e caro por design, para resistir a forca bruta sobre senhas
-- HUMANAS, que tem pouca entropia. Aqui o segredo e aleatorio de 256 bits — nao
-- ha dicionario a percorrer —, e a verificacao acontece em CADA amostra de
-- sensor. Um KDF lento no caminho de ingestao seria custo puro sem ganho.
--
-- O texto puro nao e guardado em lugar nenhum: aparece uma vez, na resposta da
-- emissao. Perdeu, emite outro — o que e barato e nao exige que o servidor
-- guarde algo que ele nao precisa poder ler.

CREATE TABLE IF NOT EXISTS device_tokens (
    device_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    ultimo_uso_em TEXT,
    revogado_em TEXT,
    revogado_por TEXT,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

-- Consulta de "quais tokens estao ativos", para o painel e para auditoria.
CREATE INDEX IF NOT EXISTS idx_device_tokens_revogado ON device_tokens (revogado_em);

-- Sem backfill, e de proposito.
--
-- Emitir tokens automaticamente para os dispositivos existentes exigiria
-- gravar o texto puro em algum lugar para alguem depois copiar para o
-- `config.h` — que e exatamente o que esta tabela evita. Os aparelhos ja
-- instalados continuam autenticando pelo `UPP_DEVICE_TOKEN` global ate que
-- cada um receba o seu (ver interface/repositories/device_tokens.py): trocar a
-- credencial de uma frota em producao de uma vez deixaria a ala inteira sem
-- monitoramento no instante do deploy.
