import { expect, type Page, type APIRequestContext } from '@playwright/test';
import fs from 'node:fs';

/**
 * Peças compartilhadas das specs. O que vem do preparador em Python
 * (`scripts/preparar_bancada_e2e.py`) chega por variável de ambiente, montada
 * em `playwright.config.ts`.
 */
export const BANCADA = {
  usuario: process.env.E2E_USUARIO!,
  senha: process.env.E2E_SENHA!,
  pacienteId: process.env.E2E_PACIENTE_ID!,
  cama: process.env.E2E_CAMA!,
  nomePaciente: 'Paciente da Bancada',
};

/** Faz login pelo formulário de verdade, não injetando token no storage.
 *
 * Injetar a sessão seria mais rápido e pularia justamente o caminho em que o
 * cookie httponly é definido — que é onde mora a diferença entre "o backend
 * emitiu" e "o navegador guardou e reenvia". */
export async function entrar(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByLabel('Usuário').fill(BANCADA.usuario);
  await page.getByLabel('Senha').fill(BANCADA.senha);
  await page.getByRole('button', { name: /entrar|acessar/i }).click();
  // A área autenticada é reconhecível pela navegação principal.
  await expect(page.getByRole('link', { name: /pacientes/i })).toBeVisible();
}

/** Envia as amostras preparadas pelo Python, pela ingestão de verdade.
 *
 * Vai por `/api` do dev server (mesma origem do navegador), então exercita o
 * mesmo proxy que a aplicação usa. */
export async function enviarAmostrasDeImobilidade(request: APIRequestContext): Promise<number> {
  const caminho = process.env.E2E_AMOSTRAS!;
  const amostras: unknown[] = JSON.parse(fs.readFileSync(caminho, 'utf-8'));
  for (const amostra of amostras) {
    const resposta = await request.post('/api/eventos', { data: amostra });
    expect(
      resposta.ok(),
      `a ingestão recusou uma amostra (${resposta.status()}): ${await resposta.text()}`,
    ).toBeTruthy();
  }
  return amostras.length;
}

/**
 * Coleta os quadros do WebSocket de alertas enquanto a página está aberta.
 *
 * Por que não basta "o alerta apareceu na lista": a tela TAMBÉM faz polling.
 * Um alerta que surge depois de alguns segundos pode ter vindo do timer, e o
 * teste passaria com o WebSocket completamente quebrado — que é exatamente o
 * defeito que este arquivo existe para pegar.
 *
 * Precisa ser instalado ANTES do `goto`: a conexão abre na montagem da página.
 */
export function observarWebSocketDeAlertas(page: Page): { quadros: string[] } {
  const quadros: string[] = [];
  page.on('websocket', (ws) => {
    if (!ws.url().includes('/ws/alerts')) return;
    ws.on('framereceived', (quadro) => quadros.push(quadro.payload.toString()));
  });
  return { quadros };
}

/** Espera um quadro `alert_new` chegar pelo WebSocket. */
export async function esperarAnuncioDeAlerta(
  quadros: string[],
  timeoutMs = 30_000,
): Promise<string> {
  const limite = Date.now() + timeoutMs;
  while (Date.now() < limite) {
    const achado = quadros.find((q) => q.includes('alert_new'));
    if (achado) return achado;
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(
    `nenhum quadro "alert_new" em ${timeoutMs}ms. Quadros recebidos:\n` +
      (quadros.length ? quadros.join('\n') : '  (nenhum — o WebSocket sequer conectou?)'),
  );
}
