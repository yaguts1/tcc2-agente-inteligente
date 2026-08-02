import { expect, test } from '@playwright/test';
import { BANCADA, entrar, leito } from './bancada';

/**
 * O básico que precisa valer antes de qualquer outra spec significar alguma
 * coisa: a aplicação sobe, autentica contra o backend de verdade e a sessão
 * sobrevive a um reload.
 *
 * Se isto quebra, os testes de tempo real falham por motivo nenhum relacionado
 * a tempo real — e é bom que a mensagem diga isso.
 */
test.describe('sessão', () => {
  // Estes dois exercitam o FORMULÁRIO, então precisam de contexto sem sessão.
  // O resto da suíte roda com o cookie que `auth.setup.ts` guardou. Somados ao
  // setup, são três tentativas de login por rodada — dentro do teto de cinco
  // por minuto que `_check_auth_rate_limit` impõe, e que não deve ser afrouxado
  // para caber o teste.
  test.describe('sem sessão prévia', () => {
    test.use({ storageState: { cookies: [], origins: [] } });

    test('login pelo formulário leva à área autenticada', async ({ page }) => {
      await entrar(page);
      await expect(page.getByRole('link', { name: /pacientes/i })).toBeVisible();
    });

    test('credencial errada não entra e explica', async ({ page }) => {
      await page.goto('/');
      await page.getByLabel('Usuário').fill(BANCADA.usuario);
      await page.getByLabel('Senha').fill('senha-errada-de-proposito');
      await page.getByRole('button', { name: /entrar|acessar/i }).click();

      // Continua no formulário — não numa tela parada nem numa área
      // autenticada por engano.
      await expect(page.getByLabel('Senha')).toBeVisible();
      await expect(page.getByRole('link', { name: /pacientes/i })).toHaveCount(0);
    });
  });

  test('a sessão sobrevive ao reload', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: /pacientes/i })).toBeVisible();
    await page.reload();
    // O cookie httponly é o que faz isto passar. Um teste que injetasse token
    // no storage não exercitaria este caminho.
    await expect(page.getByRole('link', { name: /pacientes/i })).toBeVisible();
  });

  test('os pacientes semeados aparecem na lista', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: /pacientes/i }).click();
    // Um leito por spec — ver `scripts/preparar_bancada_e2e.py`.
    for (const apelido of ['hardware', 'tempo_real', 'reconhecer', 'offline'] as const) {
      await expect(page.getByText(leito(apelido).nome)).toBeVisible();
    }
  });
});
