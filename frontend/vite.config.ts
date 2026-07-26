
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
      // Mesmo fuso que a CI do backend usa (e que o container roda). Sob
      // TZ=UTC os testes de data passariam mesmo com o bug de conversao —
      // meia-noite local e meia-noite UTC coincidem e o erro some.
      env: {
        TZ: 'America/Sao_Paulo',
      },
    },
    server: {
      port: 3000,
      open: true,
      // Proxy API requests to the backend (avoid CORS during development).
      // This will forward /api/* to the FastAPI server running on port 8000.
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
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