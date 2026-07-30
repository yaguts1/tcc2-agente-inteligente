# Roadmap — Monitor de Alertas UPP

Estado da evolução do produto. O plano original está em
`~/.claude/plans/identifique-como-a-aplica-o-luminous-sunrise.md`; este arquivo
é a versão viva, no repositório, do que já foi entregue e do que falta.

Contexto de decisão (definido com o usuário): sem prazo forçando a mão, **ainda
não em produção**, apetite alto para mudança estrutural. A ordem é por risco
técnico e dependência, não por data.

---

## Concluído

### Bloco 0 — correções de correção

Defeitos verificados, não melhorias. Tudo que veio depois mediria errado
enquanto existissem.

| # | O que era | Commit |
|---|---|---|
| 0.1 | Agenda de supressão funcionava na demo e não em produção — só o endpoint de simulação a aplicava | `bc9696f` |
| 0.2 | "Reposicionar" na tela não limpava o estado do motor: paciente ficava permanentemente sem alerta, com dashboard verde | `a76a9d7` |
| 0.3 | Fechamento por sensor e por equipe eram a mesma linha — a KPI de capa somava adesão com mobilidade do paciente | `a76a9d7` |
| 0.4 | `reconcile` escrevia em prontuário sem sessão, e no paciente errado | `3086d4e` |
| 0.5 | `/api/ws/alerts` transmitia dado clínico sem autenticação | `494dff3` |
| 0.6 | `PRAGMA foreign_keys` desligado: todo `REFERENCES` era decoração | `9974eae` |
| 0.7 | WebSocket do firmware pulava o filtro de qualidade | `3d3183f` |
| 0.8 | Teto silencioso de 1 amostra/segundo na grade | `0f8f202` |

### Bloco 1 — remodelagem do domínio

| # | Entrega | Commit |
|---|---|---|
| 1.1 | Internação como entidade; alta deixa de ser `delete`; transferência atômica que reinicia o motor; troca de leitos | `df7455b` |
| 1.2 | Unidade/ala com escopo em toda listagem, estatística, export e broadcast; tokens por dispositivo | `609f421` `b7680b8` `6d5a3db` `9609b81` `1351e0a` |
| 1.3 | Ator do reconhecimento, tempo-até-reconhecimento, motivo com taxonomia clínica, COREN | `cabb626` |
| 1.4 | Braden como entidade, definindo a janela; reavaliação vencida | `6caa322` |
| 1.5 | Orçamento de carga por sítio anatômico no lugar de corrida por postura; `pressao_pico` persistida | `ade17de` |
| 1.6 | Lesão por pressão — a variável de desfecho; incidência por 1000 paciente-dia | `6d62006` |

### Bloco 3 — parcial

| # | Entrega | Commit |
|---|---|---|
| 3.1 | Uma transação por amostra no lugar de quatro: ~26 → ~58 amostras/s com 1 thread, e concorrência passou a escalar (4 threads dão ~145/s, contra 36/s que 8 threads davam antes). Ganho de atomicidade junto | `9b59cfa` |
| 3.2 | Query do watchdog: `GROUP BY`+`MAX` → subconsulta correlacionada. 130 ms → <1 ms com 260 mil linhas | `94954f5` |

| 3.4 | Prometheus + Alertmanager raspando `/metrics`, 7 regras, `/metrics` fechado na borda | `2b3fab4` |
| 3.5 | CI publica no GHCR a mesma imagem que testou, tag imutável por SHA; VM só puxa | `bd95aec` |
| 3.6 | Property-based no decisor (14 propriedades, validadas por mutação), `--cov-fail-under=80`, ruff ampliado, ESLint do zero | `de3963b` `0bb99d2` `ee39193` |

`scripts/medir_ingestao.py` fica no repositório para a próxima medição ser
comparável.

Três defeitos que só apareceram porque as ferramentas foram ligadas:
`asyncio.create_task` sem referência forte (broadcast some sob pressão de
memória), `datetime.now()` medindo duração (salta uma hora no horário de verão),
e `console.log` despejando a lista de pacientes no console do navegador.

### Bloco 4 — parcial

| # | Entrega | Commit |
|---|---|---|
| 4.4 | Modo noturno ligado; 24 cores neutras fixas trocadas por token semântico (11 delas no popover de alertas críticos, a tela das 3h) | `9d9d0dc` |
| 4.6 | Lote audita um paciente por linha e marca-se como lote; teto de 100 e mínimo de 1 | `a3abc4e` |

### Bloco 2 — contratos

| # | Entrega | Commit |
|---|---|---|
| 2.1 | `FrontendPatient` ligado; `room`/`bed` honestamente anuláveis | `4aa3a53` |
| 2.2 | ID composto de alerta deixou de ser ambíguo e explorável | `4aa3a53` |
| 2.3 | Fonte única: tipos do front gerados do spec, com âncora bidirecional e guarda no CI | `4aa3a53` `e5dbf4b` |
| 2.4 | `/api/v1` em paralelo, com `GET /api/versoes` para descoberta | `6d43d91` |

### Segurança de implantação

| O que era | Commit |
|---|---|
| `.env` e `config.h` do firmware (senha de WiFi, tokens) iam para dentro da imagem Docker | `51345fd` |
| `dados.db` no histórico do git, em 12 commits e 3 branches | reescrita de histórico (2026-07-29) |

**Nota sobre a reescrita de histórico.** Feita com `git filter-repo`, backup
completo em `../backup-git-tcc2/antes-do-rewrite.bundle` (inclui as branches
apagadas). Três branches paradas desde out–nov/2025 foram removidas do remoto
porque ainda referenciavam os blobs. Todos os SHAs anteriores a `51345fd`
mudaram: **clones antigos precisam de `git fetch --all && git reset --hard
origin/main`**, não `git pull`.

O GitHub não coleta objetos inalcançáveis imediatamente. Os blobs podem seguir
acessíveis por SHA direto por algum tempo; para forçar, é preciso abrir pedido
ao suporte do GitHub. Como o projeto **não está em produção** e o banco só
continha dado sintético, não houve rotação de chaves — mas ao entrar em
produção, `JWT_SECRET_KEY` e `UPP_AUDIT_KEY` devem ser geradas novas, porque
estiveram dentro de uma imagem distribuível.

---

## Em aberto

### Bloco 3 — escala, operação e qualidade

- **3.3 Estado em processo bloqueia réplicas** — dedup/jitter, rate limit, cache
  e tarefas de fundo. Redis já disponível. **M**
- **3.6b mypy gradual** — a única parte de 3.6 que ficou. Vale em `nucleo/`,
  `interface/schemas.py`, `services/`, `repositories/`; não vale em
  `main.py`/`scripts/`. **M**

### Bloco 4 — entrega e uso à beira do leito

- **4.1** Notificação morre com a aba: sem service worker, sem Web Push. **M**
- **4.2** Sem escada de escalonamento — alerta de 03:00 renderiza igual às 07:00. **M**
- **4.3** Tabela de 8 colunas com `overflow-x-auto` e botões abaixo de 44px:
  não usável à beira do leito, de luva. **M**
- **4.5** Sem triagem nem "meus pacientes" (depende de 1.2 e 1.3, já prontos). **M**
- **4.7** Ações offline se perdem — a maior parte do trabalho já existe:
  `alert_id` é chave natural e `alterar_status_alerta` já é idempotente. **M**

### Bloco 5 — relatório e interoperabilidade

- **5.1 Relatório gerencial** — agora tem de onde tirar os números: adesão ×
  turno × ala × enfermeiro, distribuição de tempo-até-ack, denominador em
  paciente-hora, incidência de LPP. Falta o **turno**. **M**
- **5.2 Confiança e calibração** — `confianca` é gravada e nunca lida; sem botão
  de "falso alarme" a taxa de falso-positivo segue incognoscível. **S/M**
- **5.3 Watchdog como alerta de verdade** — hoje não tem ciclo de vida:
  sem reconhecimento, sem responsável, sem export. **M**
- **5.4 HIS/FHIR** — endpoints de leitura `Patient`/`Encounter`/`Location`
  primeiro; intake ADT depois. **M → L**

### Pontas soltas conhecidas

- `tests/`, `docs/` e `scripts_demo/` vão para a imagem Docker e não rodam em
  runtime. Peso e superfície, não segredo.
- Troca de leitos tem endpoint e não tem botão (precisa selecionar dois
  pacientes — interação diferente das outras).
- A timeline ainda grava o ator em prosa além da coluna. Não removi: é o único
  histórico dos alertas antigos.
- 45 das 66 operações seguem sem `response_model`. O mecanismo de guarda está de
  pé, então cada rota migrada ganha a proteção de graça.
- `UPP_DEVICE_TOKEN` não está definido no `.env` atual e nenhum ESP32 foi
  provisionado: a ingestão aceita qualquer origem, e o startup avisa.

---

## Sequência recomendada

1. **3.4 + 3.5** — observar a própria métrica e parar de fazer deploy de uma
   imagem que ninguém testou.
3. **5.1** — o relatório que fecha a narrativa do TCC.
