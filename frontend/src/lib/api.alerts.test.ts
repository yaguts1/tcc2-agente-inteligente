/**
 * Leitura do `X-Total-Count` em /frontend/alerts.
 *
 * O dashboard filtra em MEMÓRIA sobre o que recebeu: o que a resposta cortou
 * não existe para o filtro da tela. Sem o total, uma lista cheia é
 * indistinguível de uma lista completa, e um paciente atrasado ficaria fora
 * sem nenhum sinal.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { alertsApi } from './api';

function responderCom(itens: unknown[], headers: Record<string, string> = {}) {
  const fetchFalso = vi.fn(async (..._args: unknown[]) =>
    new Response(JSON.stringify(itens), {
      status: 200,
      headers: { 'Content-Type': 'application/json', ...headers },
    })
  );
  vi.stubGlobal('fetch', fetchFalso);
  return fetchFalso;
}

const alerta = (id: string) => ({
  id,
  patientName: 'Maria',
  room: '101',
  bed: 'A',
  lastRepositioning: '2026-01-01T08:00:00Z',
  nextRepositioning: '2026-01-01T14:00:00Z',
  riskLevel: 'high',
  status: 'pending',
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('alertsApi.getAlerts', () => {
  it('marca truncado quando o servidor tem mais do que coube', async () => {
    responderCom([alerta('a'), alerta('b')], { 'X-Total-Count': '57' });

    const pagina = await alertsApi.getAlerts();

    expect(pagina.itens).toHaveLength(2);
    expect(pagina.total).toBe(57);
    expect(pagina.truncado).toBe(true);
  });

  it('nao marca truncado quando a lista esta completa', async () => {
    responderCom([alerta('a'), alerta('b')], { 'X-Total-Count': '2' });

    const pagina = await alertsApi.getAlerts();

    expect(pagina.total).toBe(2);
    expect(pagina.truncado).toBe(false);
  });

  it('sem o header, assume lista completa em vez de inventar truncamento', async () => {
    // Backend antigo, ou proxy que remove o cabeçalho: avisar de um corte que
    // não se pode comprovar treinaria a equipe a ignorar o aviso.
    responderCom([alerta('a')]);

    const pagina = await alertsApi.getAlerts();

    expect(pagina.total).toBe(1);
    expect(pagina.truncado).toBe(false);
  });

  it('pede um teto alto, porque o filtro da tela roda sobre o que chegou', async () => {
    const fetchFalso = responderCom([], { 'X-Total-Count': '0' });

    await alertsApi.getAlerts();

    const url = String(fetchFalso.mock.calls[0][0]);
    const limite = Number(new URL(url, 'http://x').searchParams.get('limit'));
    expect(limite).toBeGreaterThanOrEqual(500);
  });

  it('repassa a janela de horas quando informada', async () => {
    const fetchFalso = responderCom([], { 'X-Total-Count': '0' });

    await alertsApi.getAlerts(72);

    const url = String(fetchFalso.mock.calls[0][0]);
    expect(new URL(url, 'http://x').searchParams.get('horas')).toBe('72');
  });
});
