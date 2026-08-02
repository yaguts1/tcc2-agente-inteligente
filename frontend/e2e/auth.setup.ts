import { test as setup } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { entrar } from './bancada';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
export const ESTADO_AUTENTICADO = path.join(AQUI, '.auth', 'estado.json');

/**
 * Autentica UMA vez e guarda os cookies para as demais specs.
 *
 * Não é otimização: `/api/auth/login` aceita 5 tentativas por minuto por IP
 * (`_check_auth_rate_limit`), e uma suíte que faz login em cada teste estoura
 * esse teto por conta própria. O sintoma é cruel — os primeiros testes passam,
 * os últimos falham na tela de login, e a falha não parece ter nada a ver com
 * autenticação.
 *
 * Baixar o limite para acomodar o teste seria enfraquecer uma proteção real
 * contra força bruta por causa do harness. O certo é o harness gastar uma
 * tentativa só.
 *
 * Os testes que PRECISAM exercitar o formulário de verdade — o login em si e a
 * credencial errada — continuam em `sessao.spec.ts`, com contexto limpo.
 */
setup('autenticar uma vez', async ({ page }) => {
  await entrar(page);
  await page.context().storageState({ path: ESTADO_AUTENTICADO });
});
