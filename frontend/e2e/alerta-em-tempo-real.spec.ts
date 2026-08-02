import { expect, test } from '@playwright/test';
import { esperarQuadro, leito, observarWebSocketDeAlertas, provocarAlerta } from './bancada';

/**
 * O alerta que manda virar o paciente precisa APARECER na tela sem recarregar.
 *
 * `tests/test_alerta_novo_chega_na_tela.py` conta a história: três defeitos
 * independentes congelavam a lista, e bastava um. O motor não anunciava
 * (Python); o front desligava o polling ao conectar o WebSocket (TypeScript); e
 * o handler usava `prev.map`, que atualiza item existente e não insere
 * (TypeScript). O teste de lá cobre o primeiro de verdade e os outros dois só
 * por descrição — ele não tem navegador.
 *
 * Este arquivo é o que reprova os dois últimos. Atravessa a jornada inteira numa
 * direção só: HTTP → ingestão → filtro → motor de alertas → broadcast →
 * WebSocket → React → DOM.
 */
test('alerta novo chega na tela sem reload, e é de verdade', async ({ page, request }) => {
  const alvo = leito('tempo_real');

  // O observador precisa existir antes da navegação: a conexão do WebSocket
  // abre na montagem da aplicação.
  const { quadros } = observarWebSocketDeAlertas(page);

  await page.goto('/');

  // Ponto de partida honesto: se este paciente já tivesse alerta, a asserção
  // final não provaria que ELE chegou agora.
  await expect(page.getByText(alvo.nome)).toHaveCount(0);

  // A partir daqui a página NÃO é tocada. Nada de reload, nada de clique: o
  // único caminho para a lista mudar é o servidor empurrar.
  expect(await provocarAlerta(request, 'tempo_real')).toBeGreaterThan(0);

  // 1) O anúncio chegou pelo WebSocket.
  //
  // Sem esta asserção o teste passaria com o WebSocket quebrado, porque a tela
  // também faz polling — o alerta apareceria alguns segundos depois pelo timer
  // e ninguém notaria a diferença. É exatamente esse encobrimento que deixou o
  // defeito original invisível.
  expect(await esperarQuadro(quadros, 'alert_new')).toContain(alvo.paciente_id);

  // 2) E virou linha na tela, sem nenhuma navegação.
  await expect(page.getByText(alvo.nome).first()).toBeVisible();

  // 3) O alerta existe no servidor, não só no estado do React. Um alerta que
  //    vive apenas na memória do navegador some aqui.
  await page.reload();
  await expect(page.getByText(alvo.nome).first()).toBeVisible();
});
