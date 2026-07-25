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
  components/   pages/, alerts/, patients/, auth/, ui/ (wrappers Radix), shared/
  contexts/     AlertsContext (lista de alertas), WebSocketContext
  hooks/        useAuth, usePolling, useWebSocket, useCriticalAlerts, ...
  lib/          api.ts (chamadas HTTP), storage.ts
```

## Limitações conhecidas

- **`src/index.css` é um artefato gerado do Tailwind v4 commitado como fonte**, e
  o `tailwindcss` não está no `package.json`. Na prática, qualquer classe
  utilitária nova que você escrever **não terá efeito** — e isso falha em
  silêncio. A fonte autoral é `src/styles/globals.css`, hoje órfã. Restaurar o
  toolchain está pendente.
- Não há router: a navegação é `useState` sobre um `switch` em `App.tsx`, logo
  não há URLs por página, histórico do browser nem code splitting (o bundle sai
  em um único chunk de ~434 kB).
