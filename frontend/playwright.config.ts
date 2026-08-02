import { defineConfig, devices } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// `package.json` marca o pacote como `"type": "module"`, então não existe
// `__dirname` — o equivalente em ESM.
const AQUI = path.dirname(fileURLToPath(import.meta.url));

/**
 * E2E de navegador: a terceira ponta da validação.
 *
 * O projeto já validava o backend, com pytest, e o dispositivo, com o ESP32
 * ligado na serial. A tela era a ponta sem verificação de integração nenhuma —
 * os testes de UI existentes são de componente, em jsdom, com o `fetch` e o
 * WebSocket dublados. Eles não podem pegar o caso que motivou este arquivo: o
 * alerta que o motor emite, atravessa o WebSocket e precisa APARECER na lista
 * sem recarregar a página.
 *
 * `tests/test_alerta_novo_chega_na_tela.py` documenta três defeitos que, juntos,
 * congelavam a lista na tela: o motor não anunciava, o front desligava o polling
 * ao conectar o WS, e o handler usava `prev.map` (que atualiza, não insere).
 * Os dois primeiros são visíveis do Python. O terceiro é puramente do navegador,
 * e só um teste como estes reprova.
 *
 * PEÇAS QUE SOBEM
 * ---------------
 * 1. banco descartável, semeado por `scripts.preparar_bancada_e2e` (Python, com
 *    as mesmas funções da aplicação — ver o docstring de lá);
 * 2. uvicorn de verdade em :8010, ligado a esse banco;
 * 3. o dev server do Vite em :3100, cujo proxy `/api` já encaminha HTTP **e**
 *    WebSocket (`ws: true`) — o que dá uma origem só e evita CORS.
 *
 * Rodar:  npm run e2e          (headless)
 *         npm run e2e:ui       (modo interativo)
 */

const RAIZ = path.resolve(AQUI, '..');

// Portas próprias, fora das habituais de propósito.
//
// A 8000 costuma estar ocupada pelo container `upp_app` (docker compose) e a
// 3000 pelo `npm run dev` de quem está trabalhando. Um harness que exige
// derrubar a stack para rodar é um harness que ninguém roda — e, pior, se
// `reuseExistingServer` estivesse ligado, ele rodaria contra o container e o
// banco DE VERDADE, semeando paciente de teste em cima de dado real.
// A porta da API sai do `config.h` do FIRMWARE, que é onde ela está compilada
// para dentro do ESP32. A spec de hardware faz o aparelho falar com este mesmo
// backend; fixar o valor aqui também criaria dois lugares para a mesma decisão,
// e o dia em que divergissem daria um replay parado sem explicação.
function portaDoFirmware(): number | null {
  const config = path.join(RAIZ, 'firmware', 'esp32_replay', 'config.h');
  if (!fs.existsSync(config)) return null;
  const m = fs.readFileSync(config, 'utf-8').match(/^\s*#define\s+SERVER_PORT\s+(\d+)/m);
  return m ? Number(m[1]) : null;
}

const PORTA_API = Number(process.env.E2E_API_PORT) || portaDoFirmware() || 8010;
const PORTA_WEB = Number(process.env.E2E_WEB_PORT || 3100);

/**
 * Semeia o banco AGORA, no carregamento da configuração.
 *
 * Precisa ser aqui, e não num `globalSetup`: o `webServer` do backend recebe
 * `UPP_DB_PATH` como variável de ambiente, e esse objeto é montado quando a
 * configuração é lida. Um globalSetup rodaria depois de o uvicorn já ter subido
 * apontando para outro lugar.
 */
function semearBancada(): { db: string; descricao: string } {
  const saida = execFileSync('python', ['-m', 'scripts.preparar_bancada_e2e'], {
    cwd: RAIZ,
    encoding: 'utf-8',
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  });
  const descricao = saida.trim().split(/\r?\n/).pop() ?? '';
  if (!descricao || !fs.existsSync(descricao)) {
    throw new Error(`preparar_bancada_e2e não devolveu a descrição da bancada:\n${saida}`);
  }
  return { db: JSON.parse(fs.readFileSync(descricao, 'utf-8')).db, descricao };
}

const BANCADA = semearBancada();

// O caminho do JSON é o contrato entre o preparador em Python e as specs em
// TypeScript. Uma variável só, e a estrutura mora no arquivo — ver `bancada.ts`.
process.env.E2E_BANCADA = BANCADA.descricao;

export default defineConfig({
  testDir: './e2e',
  // Um worker: os testes compartilham UM backend e UM banco. Paralelizar exigiria
  // um banco por worker, e o alvo aqui é a integração, não o volume.
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // Rastro só do que falhou: abrir `npx playwright show-trace` num teste de
  // tempo real mostra exatamente quando cada quadro do WebSocket chegou.
  use: {
    baseURL: `http://localhost:${PORTA_WEB}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  projects: [
    // Gasta UMA das 5 tentativas de login por minuto que o backend permite, e
    // as demais specs reaproveitam o cookie. Ver `e2e/auth.setup.ts`.
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: path.join(AQUI, 'e2e', '.auth', 'estado.json'),
      },
      dependencies: ['setup'],
    },
  ],

  webServer: [
    {
      // `0.0.0.0`, e não `127.0.0.1`: o ESP32 da spec de hardware alcança este
      // backend pela LAN. Em loopback o aparelho falaria com o vazio e o replay
      // ficaria parado em OCIOSO para sempre.
      command:
        `python -m uvicorn interface.web:app --host 0.0.0.0 --port ${PORTA_API} --log-level warning`,
      cwd: RAIZ,
      port: PORTA_API,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        UPP_DB_PATH: BANCADA.db,
        APP_PREFIX: '',
        ENVIRONMENT: 'development',
        BACKUP_ON_START: '0',
        // A bancada não provisiona dispositivo: a ingestão precisa aceitar os
        // eventos que as specs enviam por HTTP. Explícito para não herdar um
        // token do shell e transformar todo POST em 401.
        UPP_DEVICE_TOKEN: '',
      },
    },
    {
      command: `npm run dev -- --port ${PORTA_WEB} --strictPort`,
      cwd: AQUI,
      port: PORTA_WEB,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { E2E: '1', VITE_API_ALVO: `http://127.0.0.1:${PORTA_API}` },
    },
  ],
});
