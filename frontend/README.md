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
| `npm run test` | Testes (Vitest) |

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
