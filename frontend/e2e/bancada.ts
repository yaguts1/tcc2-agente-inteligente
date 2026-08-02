import { expect, type APIRequestContext, type Page } from '@playwright/test';
import fs from 'node:fs';

/**
 * A bancada, como o preparador em Python a descreveu.
 *
 * Estrutura em `scripts/preparar_bancada_e2e.py`. Cada spec que faz nascer um
 * alerta tem o próprio leito: o motor não reabre alerta já aberto e respeita
 * cooldown, então specs compartilhando paciente ficariam acopladas à ordem de
 * execução.
 */
type Leito = {
  paciente_id: string;
  nome: string;
  cama: string;
  amostras: unknown[];
};

type Bancada = {
  db: string;
  usuario: string;
  senha: string;
  leitos: Record<string, Leito>;
};

export const BANCADA: Bancada = JSON.parse(fs.readFileSync(process.env.E2E_BANCADA!, 'utf-8'));

export function leito(apelido: 'hardware' | 'tempo_real' | 'reconhecer' | 'offline'): Leito {
  const achado = BANCADA.leitos[apelido];
  if (!achado) {
    throw new Error(
      `leito "${apelido}" não existe na bancada. Disponíveis: ${Object.keys(BANCADA.leitos).join(', ')}`,
    );
  }
  return achado;
}

/**
 * Faz login pelo formulário de verdade, não injetando token no storage.
 *
 * Injetar a sessão seria mais rápido e pularia justamente o caminho em que o
 * cookie httponly é definido — que é onde mora a diferença entre "o backend
 * emitiu" e "o navegador guardou e reenvia".
 */
export async function entrar(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByLabel('Usuário').fill(BANCADA.usuario);
  await page.getByLabel('Senha').fill(BANCADA.senha);
  await page.getByRole('button', { name: /entrar|acessar/i }).click();
  await expect(page.getByRole('link', { name: /pacientes/i })).toBeVisible();
}

/**
 * Faz nascer um alerta de imobilidade no leito indicado, pela ingestão de
 * verdade.
 *
 * Vai por `/api` do dev server (mesma origem do navegador), então exercita o
 * mesmo proxy que a aplicação usa.
 */
export async function provocarAlerta(
  request: APIRequestContext,
  apelido: Parameters<typeof leito>[0],
): Promise<number> {
  const alvo = leito(apelido);
  for (const amostra of alvo.amostras) {
    const resposta = await request.post('/api/eventos', { data: amostra });
    expect(
      resposta.ok(),
      `a ingestão recusou uma amostra (${resposta.status()}): ${await resposta.text()}`,
    ).toBeTruthy();
  }
  return alvo.amostras.length;
}

/**
 * Coleta os quadros do WebSocket de alertas enquanto a página está aberta.
 *
 * Por que não basta "o alerta apareceu na lista": a tela TAMBÉM faz polling.
 * Um alerta que surge depois de alguns segundos pode ter vindo do timer, e o
 * teste passaria com o WebSocket completamente quebrado — que é exatamente o
 * defeito que este harness existe para pegar.
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

/** Espera um quadro do tipo pedido chegar pelo WebSocket. */
export async function esperarQuadro(
  quadros: string[],
  tipo: 'alert_new' | 'alert_update',
  timeoutMs = 30_000,
): Promise<string> {
  const limite = Date.now() + timeoutMs;
  while (Date.now() < limite) {
    const achado = quadros.find((q) => q.includes(tipo));
    if (achado) return achado;
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(
    `nenhum quadro "${tipo}" em ${timeoutMs}ms. Quadros recebidos:\n` +
      (quadros.length ? quadros.join('\n') : '  (nenhum — o WebSocket sequer conectou?)'),
  );
}

/**
 * O status que o SERVIDOR tem para o leito, ou `null` se não há alerta.
 *
 * Consultado pelo `request`, que é um contexto HTTP à parte do navegador — e é
 * o que permite perguntar ao backend enquanto a página está offline.
 */
export async function statusNoServidor(
  request: APIRequestContext,
  apelido: Parameters<typeof leito>[0],
): Promise<string | null> {
  const resposta = await request.get('/api/frontend/alerts');
  expect(resposta.ok(), `GET /api/frontend/alerts falhou: ${resposta.status()}`).toBeTruthy();
  const itens: Array<{ patientName?: string; status?: string }> = await resposta.json();
  const nome = leito(apelido).nome;
  return itens.find((a) => a.patientName === nome)?.status ?? null;
}

/** A linha da tabela correspondente a um leito. */
export function linhaDoPaciente(page: Page, apelido: Parameters<typeof leito>[0]) {
  return page.getByRole('row').filter({ hasText: leito(apelido).nome });
}
