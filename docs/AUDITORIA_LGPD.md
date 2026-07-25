# Trilha de auditoria (LGPD)

Dado de saúde é **dado pessoal sensível** (LGPD, Art. 5º, II). Este sistema
registra os acessos a dado de paciente para atender:

- **Art. 37** — o controlador mantém registro das operações de tratamento;
- **Art. 46** — medidas de segurança e rastreabilidade do acesso;
- **Art. 48** — comunicar um incidente exige saber **quais titulares** foram
  expostos, o que só é possível se as *leituras* também forem registradas.

## O que é registrado

Toda requisição a rotas de dado clínico (`/api/pacientes`, `/api/frontend/alerts`,
`/api/timeline`, `/api/stats`, exportações, `/api/admin`, `/api/usuarios`,
`/api/devices`, `/api/auditoria`) gera uma entrada com:

| Campo | Conteúdo |
|---|---|
| `ts` / `ts_ms` | Quando (UTC naive, mesma convenção do resto do banco) |
| `usuario` / `papel` | Quem (do JWT; `null` em acesso anônimo) |
| `acao` / `metodo` / `rota` | O que |
| `paciente_id` | Titular do dado, extraído da rota quando identificável |
| `status` / `negado` | Resultado; `negado` marca 401/403 |
| `ip` | Origem real (via `X-Forwarded-For` de proxy confiável) |
| `duracao_ms` | Tempo de processamento |

**Leituras contam.** Em prontuário, "quem consultou os dados deste paciente" é
a pergunta central — registrar apenas escritas deixaria de fora justamente o
acesso indevido mais comum.

**Tentativas negadas contam.** 401/403 são o sinal mais útil para detectar uso
indevido, e por isso são marcadas e filtráveis.

## O que **não** é registrado

- **Corpo da requisição ou da resposta.** Além do volume, o corpo carrega
  justamente o dado sensível que a trilha existe para proteger. O objetivo é
  saber *quem acessou o quê e quando*, não duplicar o prontuário no log.
- **`/api/auth/login`.** A senha vai no corpo; registrar essa rota arriscaria
  gravar credencial. O resultado do login aparece nos logs estruturados.
- **`/healthz`, métricas e assets da SPA.** Não tocam dado de paciente e
  inundariam a trilha, diluindo o que importa.

## Como consultar

Restrito a `admin` — a própria trilha revela padrões de acesso e
identificadores de pacientes.

```bash
# Quem acessou os dados deste paciente? (a pergunta que a LGPD exige responder)
GET /api/auditoria?paciente_id=PAC-0001

# O que este usuário fez? (investigação de uso indevido)
GET /api/auditoria?usuario=enfermeira

# Tentativas recusadas
GET /api/auditoria?apenas_negados=true

# Janela de tempo (epoch em ms) e paginação
GET /api/auditoria?desde_ms=...&ate_ms=...&limit=200&offset=0
```

## Retenção

`expurgar_anteriores_a(db_path, ts_ms)` remove entradas anteriores a um
instante. Não há expurgo automático: a LGPD pede que o dado não seja mantido
além do necessário (Art. 15/16), mas o prazo adequado é **política da
instituição** — um prazo arbitrário embutido no código seria pior que a
decisão explícita.

## Limitações conhecidas

- **A trilha não é à prova de adulteração.** Fica no mesmo SQLite do resto do
  sistema; quem tiver acesso ao arquivo pode editá-la. Para uso regulatório
  sério, o próximo passo é encadeamento por hash ou envio para armazenamento
  append-only externo.
- **Escrita síncrona por requisição** (numa thread, para não bloquear o event
  loop). Custa ~10 ms por requisição auditada. Sob carga alta, o caminho é um
  buffer com escrita em lote.
- **`paciente_id` vem da rota.** Endpoints que devolvem vários pacientes (ex.:
  listagem de alertas) registram o acesso, mas sem discriminar cada titular
  retornado.
