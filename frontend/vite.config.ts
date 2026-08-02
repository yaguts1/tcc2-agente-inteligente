
  import { defineConfig } from 'vite';
  import react from '@vitejs/plugin-react-swc';
  import tailwindcss from '@tailwindcss/vite';
  import path from 'path';

  export default defineConfig({
    plugins: [react(), tailwindcss()],
    resolve: {
      extensions: ['.js', '.jsx', '.ts', '.tsx', '.json'],
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      target: 'esnext',
      outDir: 'build',
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/setupTests.ts',
      // `e2e/` é do Playwright, não do Vitest. Os dois reconhecem `*.spec.ts`,
      // então sem esta linha o `vitest` coletava as specs de navegador e
      // quebrava em `test.describe` — que existe nas duas ferramentas com
      // assinaturas diferentes.
      exclude: ['**/node_modules/**', '**/dist/**', '**/build/**', 'e2e/**'],
      // Mesmo fuso que a CI do backend usa (e que o container roda). Sob
      // TZ=UTC os testes de data passariam mesmo com o bug de conversao —
      // meia-noite local e meia-noite UTC coincidem e o erro some.
      env: {
        TZ: 'America/Sao_Paulo',
      },
    },
    server: {
      port: 3000,
      // O Playwright sobe este mesmo dev server e dirige o proprio navegador.
      // Com `open: true` cada rodada tambem escancarava uma aba no navegador do
      // desenvolvedor, que nao participa do teste e ainda rouba o foco.
      open: process.env.E2E !== '1',
      // Proxy API requests to the backend (avoid CORS during development).
      // This will forward /api/* to the FastAPI server running on port 8000.
      proxy: {
        '/api': {
          // Configurável porque o E2E de navegador sobe o proprio backend, e a
          // porta 8000 costuma estar ocupada pelo container `upp_app` — o
          // harness nao pode exigir que a stack do desenvolvedor seja derrubada
          // para rodar. Sem variavel, o comportamento e o de sempre.
          target: process.env.VITE_API_ALVO || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
          ws: true,
          // Rewrite cookie domain when backend sets cookies for a different host
          // so the browser stores the cookie for the dev server origin (localhost:3000).
          // An empty string strips the Domain attribute making it a host-only cookie.
          cookieDomainRewrite: '',
        },
      },
    },
  });