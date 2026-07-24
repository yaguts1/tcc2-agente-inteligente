
  import { defineConfig } from 'vite';
  import react from '@vitejs/plugin-react-swc';
  import path from 'path';

  export default defineConfig({
    plugins: [react()],
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