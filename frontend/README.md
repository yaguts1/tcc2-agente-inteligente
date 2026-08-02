# Frontend — Sistema de Alertas de Reposicionamento

SPA em React 18 + TypeScript + Vite. Consome a API FastAPI da raiz do
repositório e é servida por ela em produção (o build vai para `frontend/build`
e o backend o publica sob o prefixo `APP_PREFIX`, por padrão `/TCC`).

## Desenvolvimento

```bash
npm install
npm run dev        # Vite em http://localhost:5173 (proxy para a API na 8000)
```

O backend precisa estar no ar (`uvicorn interface.web:app --reload` a partir da
raiz), ou use o Docker: `docker compose up --build` sobe tudo junto.

## Scripts

| Comando | O que faz |
|---|---|
| `npm run dev` | Servidor de desenvolvimento (Vite) |
| `npm run build` | Build de produção em `build/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run test` | Testes de componente (Vitest, jsdom) |
| `npm run e2e` | E2E de navegador (Playwright) |
| `npm run e2e:ui` | O mesmo, em modo interativo |
| `npm run e2e:report` | Abre o relatório da última rodada |

## E2E de navegador

`npm run test` roda em jsdom, com `fetch` e WebSocket dublados: valida
componentes, não integração. `npm run e2e` sobe a coisa inteira e dirige um
Chromium de verdade.

```bash
npx playwright install chromium   # uma vez
npm run e2e
```

Não é preciso preparar nada: a configuração semeia um banco descartável
(`scripts/preparar_bancada_e2e.py`, em Python, usando as mesmas funções da
aplicação), sobe um uvicorn próprio e um dev server próprio.

**Portas 8010 e 3100**, não 8000 e 3000. O container `upp_app` costuma ocupar a
8000 e o `npm run dev` de quem está trabalhando ocupa a 3000; um harness que
exige derrubar a stack para rodar é um harness que ninguém roda. E
`reuseExistingServer` está desligado de propósito: aproveitar um servidor já no
ar faria a suíte semear paciente de teste dentro do banco de verdade.

### Um leito por spec

`scripts/preparar_bancada_e2e.py` cria três pacientes, um por spec que precisa
fazer nascer um alerta. O motor não reabre alerta já aberto e respeita cooldown:
specs disputando o mesmo paciente ficariam acopladas à ordem de execução — a
segunda passaria só porque a primeira rodou antes.

Cada leito tem o **próprio `device_id`**. O servidor resolve de quem é a amostra
pelo dispositivo, não pelo `paciente_id` do payload; com um `device_id`
compartilhado, as amostras dos outros leitos são atribuídas ao primeiro paciente
e somem na PK da `grade` — **respondendo 2xx em todas as requisições**.

E os nomes dos pacientes não contêm palavra que apareça em botão da interface:
"Paciente Reconhecer" fazia o botão "Assumir Paciente Reconhecer" casar com o
seletor do botão "Reconhecer".

### O teste que justifica tudo isso

`e2e/alerta-em-tempo-real.spec.ts` percorre HTTP → ingestão → filtro → motor de
alertas → broadcast → WebSocket → React → DOM, e afirma **duas** coisas: que o
quadro `alert_new` chegou pelo WebSocket, e que virou linha na tela sem nenhum
reload. A primeira asserção existe porque a tela também faz polling — sem ela, o
teste passaria com o WebSocket quebrado, que é justamente o encobrimento que
manteve o defeito original invisível (ver
`tests/test_alerta_novo_chega_na_tela.py`).

Verificado reintroduzindo o defeito histórico (`alert_new` tratado com
`prev.map`, que atualiza e não insere): a spec reprova, com o WebSocket
recebendo o quadro normalmente e a lista seguindo vazia.

### A fila offline, com a rede cortada de verdade

`e2e/fila-offline.spec.ts` é a outra spec que só existe por causa do navegador.
`AlertsContext.offline.test.tsx` cobre a mesma feature em jsdom, mas lá o
"offline" é um `fetch` dublado que rejeita — isso testa o tratamento do erro,
não a condição. Aqui `context.setOffline(true)` corta a rede de verdade e a fila
é a IndexedDB de verdade, a mesma que o tablet da ala usa.

A asserção que dá sentido ao teste é a do meio: **enquanto a rede está cortada,
o servidor não pode ter o reconhecimento**. Ela é possível porque o `request` do
Playwright é um contexto HTTP à parte do navegador e continua alcançando o
backend. Sem ela, um clique que passasse antes do corte produziria o mesmo
desfecho final e o teste "passaria" sem nunca ter exercitado a fila.

Verificado quebrando `enfileirar()` para descartar a ação: a spec reprova com
"a ação registrada offline nunca chegou ao servidor".

### Rate limit de login

`/api/auth/login` aceita 5 tentativas por minuto por IP. `e2e/auth.setup.ts`
autentica **uma vez** e as demais specs reaproveitam o cookie; só os dois testes
que exercitam o formulário usam contexto limpo. Uma suíte que fizesse login em
cada teste estouraria o teto sozinha — e o sintoma seria cruel: os primeiros
testes passam, os últimos falham na tela de login, e nada aponta para
autenticação.

## Autenticação

As rotas de dados clínicos exigem sessão. O login devolve um cookie `httpOnly`
`access_token` que o browser envia sozinho — não há token a guardar no
`localStorage`. A primeira conta da instalação pode ser criada livremente; a
partir daí, criar conta exige sessão ativa ou `X-Register-Token`.

## Estrutura

```
src/
  components/   pages/, admin/, alerts/, patients/, auth/, ui/ (wrappers Radix), shared/
  contexts/     AlertsContext (lista de alertas), WebSocketContext
  hooks/        useAuth, usePolling, useWebSocket, useCriticalAlerts, ...
  lib/          api.ts (chamadas HTTP), storage.ts
```

## Estilos

A fonte autoral é `src/styles/globals.css`, importada por `main.tsx`. O
Tailwind v4 roda pelo plugin `@tailwindcss/vite` (ver `vite.config.ts`), então
classe utilitária nova tem efeito normalmente.

> Esta seção existia como "Limitação conhecida" afirmando o oposto — que
> `src/index.css` era um artefato gerado commitado como fonte, que o
> `tailwindcss` não estava no `package.json` e que qualquer classe nova
> falharia em silêncio. Já não é verdade: o arquivo não existe mais, a
> dependência está declarada e o `globals.css` deixou de ser órfão. Ficou
> registrado porque um README que declara algo quebrado quando está funcionando
> custa tempo de quem chega — ou faz alguém "consertar" o que está certo.

## Rotas e bundle

A navegação usa `react-router` (`BrowserRouter` em `App.tsx`), com uma rota por
página e `lazy()` em cada uma. Ou seja: há URL por página, histórico do browser
e code splitting — o build sai em chunks separados (`DashboardPage`,
`TimelinePage`, `PatientsPage`, `AdminPage`) além do chunk comum.

> Também descrito antes como limitação ("a navegação é `useState` sobre um
> `switch`, sem URLs, sem histórico, bundle único de ~434 kB"), igualmente
> superado.

## Limitações conhecidas

- Os testes cobrem a camada de alertas, admin e as conversões de data; páginas
  inteiras (Dashboard, Pacientes) ainda não têm teste de componente.
