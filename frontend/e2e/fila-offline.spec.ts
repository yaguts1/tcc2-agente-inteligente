import { expect, test } from '@playwright/test';
import {
  esperarQuadro,
  linhaDoPaciente,
  observarWebSocketDeAlertas,
  provocarAlerta,
  statusNoServidor,
} from './bancada';

/**
 * A fila offline, com a rede cortada de verdade.
 *
 * `src/lib/filaOffline.ts` explica por que ela existe: Wi-Fi hospitalar cai em
 * corredor, escada e elevador — não é caso de borda, é a topologia. Quem marcou
 * quatro pacientes numa zona morta perdia os quatro, e sem saber quais. O custo
 * não é o clique: é a enfermeira acreditar que registrou e o prontuário dizer
 * que não, com a discrepância aparecendo na auditoria semanas depois.
 *
 * POR QUE ESTA SPEC PRECISA DE NAVEGADOR
 * --------------------------------------
 * `AlertsContext.offline.test.tsx` cobre a mesma feature em jsdom, mas lá o
 * "offline" é um dublê: o `fetch` é substituído por um que rejeita. Isso testa
 * o código de tratamento, não a condição. Aqui `context.setOffline(true)` corta
 * a rede do navegador de verdade, e a fila é a IndexedDB de verdade — a mesma
 * que o tablet da ala usa.
 *
 * O `request` do Playwright é um contexto HTTP à parte do navegador, então
 * continua alcançando o backend enquanto a página está offline. É o que permite
 * a asserção que dá sentido ao teste: enquanto a rede está cortada, o servidor
 * **não** pode ter o reconhecimento.
 */
test('ação feita offline sobrevive e chega ao servidor quando a rede volta', async ({
  page,
  request,
  context,
}) => {
  const { quadros } = observarWebSocketDeAlertas(page);
  await page.goto('/');
  await provocarAlerta(request, 'offline');
  await esperarQuadro(quadros, 'alert_new');

  const linha = linhaDoPaciente(page, 'offline');
  await expect(linha).toHaveCount(1);
  expect(await statusNoServidor(request, 'offline')).toBe('pending');

  // ---- a enfermeira entra no elevador ----
  await context.setOffline(true);

  await linha.getByRole('button', { name: 'Reconhecer', exact: true }).click();

  // O servidor NÃO pode ter recebido nada: é o que torna o resto do teste
  // significativo. Sem esta asserção, um clique que passou pela rede antes do
  // corte produziria o mesmo desfecho final e o teste "passaria" sem nunca ter
  // exercitado a fila.
  expect(await statusNoServidor(request, 'offline')).toBe('pending');

  // ---- e sai do elevador ----
  await context.setOffline(false);

  // A fila drena sozinha: no evento `online` e, enquanto houver pendências, a
  // cada 20 s (`useFilaOffline.INTERVALO_MS`) — porque o evento sozinho não
  // basta, ele dispara quando a interface sobe e não quando o servidor fica
  // alcançável. O teto aqui cobre um ciclo inteiro com folga.
  await expect
    .poll(() => statusNoServidor(request, 'offline'), {
      timeout: 45_000,
      message: 'a ação registrada offline nunca chegou ao servidor',
    })
    .toBe('acknowledged');

  // E a tela reflete o que o servidor tem, depois de um recarregamento limpo.
  await page.reload();
  await expect(
    linhaDoPaciente(page, 'offline').getByRole('button', { name: 'Reconhecer', exact: true }),
  ).toBeDisabled();
});
