import { expect, test } from '@playwright/test';
import {
  esperarQuadro,
  linhaDoPaciente,
  statusNoServidor,
  observarWebSocketDeAlertas,
  provocarAlerta,
} from './bancada';

/**
 * Reconhecer um alerta: o outro sentido da conversa.
 *
 * `alert_new` insere; `alert_update` atualiza uma linha existente — são reações
 * diferentes na tela, e o `test_alerta_novo_chega_na_tela.py` afirma que os dois
 * tipos existem justamente por isso. Aqui a mudança é verificada onde importa:
 * no botão, na linha e no servidor.
 *
 * Leito próprio (`reconhecer`, C-02) para não disputar o alerta com as outras
 * specs — o motor não reabre alerta já aberto.
 */
test('reconhecer muda o estado na tela e no servidor', async ({ page, request }) => {
  const { quadros } = observarWebSocketDeAlertas(page);

  await page.goto('/');
  await provocarAlerta(request, 'reconhecer');
  await esperarQuadro(quadros, 'alert_new');

  const linha = linhaDoPaciente(page, 'reconhecer');
  // Exatamente uma: a serie e curta o bastante para fechar UMA janela de
  // imobilidade. Duas linhas iguais tornariam ambigua toda assercao abaixo.
  await expect(linha).toHaveCount(1);

  const reconhecer = linha.getByRole('button', { name: 'Reconhecer', exact: true });
  await expect(reconhecer).toBeEnabled();
  await reconhecer.click();

  // O botão desabilita quando o status vira `acknowledged` — é o sinal de que a
  // linha reagiu, e não apenas de que o clique aconteceu.
  await expect(reconhecer).toBeDisabled();

  // E o servidor concorda. Sem isto, um reconhecimento que só mudou o estado
  // local passaria: a enfermeira veria "reconhecido" e a auditoria, semanas
  // depois, diria que ninguém atendeu.
  expect(await statusNoServidor(request, 'reconhecer')).toBe('acknowledged');

  await page.reload();
  await expect(
    linhaDoPaciente(page, 'reconhecer').getByRole('button', { name: 'Reconhecer', exact: true }),
  ).toBeDisabled();
});
