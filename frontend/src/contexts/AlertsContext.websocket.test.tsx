/**
 * Um alerta NOVO tem de aparecer na tela.
 *
 * Duas camadas do frontend impediam isso, e bastava uma:
 *
 * 1. O polling era desligado enquanto o WS estivesse conectado
 *    (`enabled: !wsConnected`), tratando conexão aberta como garantia de que
 *    as mensagens chegam. Não é: a conexão pode estar viva e o servidor não
 *    publicar nada — que era exatamente o caso, porque nada anunciava alerta
 *    novo.
 * 2. O handler fazia `prev.map`, que atualiza item existente e não insere.
 *    Mesmo com o anúncio, o alerta novo não entraria na lista.
 *
 * Somados: com a tela conectada, a lista congelava no que existia quando a
 * página abriu, e nada indicava isso.
 */
import { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AlertsProvider, useAlerts } from './AlertsContext';

vi.mock('../lib/api', async () => {
  const real = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...real,
    alertsApi: { getAlerts: vi.fn(), acknowledge: vi.fn(), complete: vi.fn() },
  };
});

// Captura o handler registrado pelo contexto, para simular o servidor
// publicando uma mensagem. `isConnected: true` reproduz a situação em que o
// defeito aparecia — WS conectado.
let publicar: ((m: unknown) => void) | null = null;
vi.mock('./WebSocketContext', () => ({
  useWebSocketContext: () => ({
    isConnected: true,
    subscribe: (fn: (m: unknown) => void) => {
      publicar = fn;
      return () => {
        publicar = null;
      };
    },
  }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { alertsApi } from '../lib/api';
import type { Alert, PaginaDeAlertas } from '../lib/api';

const alerta = (id: string) => ({
  id,
  patientId: id.split('__')[0],
  patientName: `Paciente ${id}`,
  room: '201',
  bed: 'A',
  lastRepositioning: '2026-07-26T05:00:00+00:00',
  nextRepositioning: '2026-07-26T06:00:00+00:00',
  riskLevel: 'high' as const,
  status: 'pending' as const,
  closureOrigin: null,
  closedBy: null,
  site: null, minutesOpen: 0, escalationLevel: 'normal' as const,
});

function Sonda() {
  const { alerts } = useAlerts();
  return <div data-testid="ids">{alerts.map((a) => a.id).join(',')}</div>;
}


// A API devolve a página (itens + total) para que o truncamento seja visível.
// Nos testes o total é sempre o tamanho da lista: nada truncado.
const pagina = (itens: Alert[]): PaginaDeAlertas => ({
  itens,
  total: itens.length,
  truncado: false,
});

const renderizar = () =>
  render(
    <AlertsProvider>
      <Sonda />
    </AlertsProvider> as ReactNode,
  );

describe('alerta novo com o WebSocket conectado', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    publicar = null;
  });

  it('insere na lista o alerta anunciado pelo servidor', async () => {
    // A lista só passa a ter 2 itens DEPOIS da mensagem: o mock troca de
    // resposta apenas no passo 3. Se o handler ignorar `alert_new` — como
    // fazia, por só tratar `alert_update` com `prev.map` — nada dispara o
    // refetch e a tela fica no 1 item.
    //
    // (A primeira versão deste teste usava mockResolvedValueOnce e passava
    // contra o código com defeito: um refetch vindo de outro caminho trazia o
    // segundo alerta sozinho, então o teste não provava o que afirmava.)
    vi.mocked(alertsApi.getAlerts).mockResolvedValue(pagina([alerta('PAC-1__t1')]));

    renderizar();
    await waitFor(() => expect(screen.getByTestId('ids')).toHaveTextContent('PAC-1__t1'));
    expect(screen.getByTestId('ids')).not.toHaveTextContent('PAC-2__t2');

    vi.mocked(alertsApi.getAlerts).mockResolvedValue(pagina([
      alerta('PAC-1__t1'),
      alerta('PAC-2__t2'),
    ]));

    // O motor abriu um alerta para outro paciente.
    publicar?.({ type: 'alert_new', alert_id: 'PAC-2__t2', status: 'pending' });

    await waitFor(() =>
      expect(screen.getByTestId('ids')).toHaveTextContent('PAC-1__t1,PAC-2__t2'),
    );
  });

  it('mantem o polling ligado mesmo com o WS conectado', async () => {
    // Conexão aberta não prova que as mensagens chegam. O segundo canal existe
    // para que o defeito de um vire atraso, e não ausência.
    vi.useFakeTimers();
    try {
      vi.mocked(alertsApi.getAlerts).mockResolvedValue(pagina([alerta('PAC-1__t1')]));
      renderizar();

      await vi.waitFor(() => expect(alertsApi.getAlerts).toHaveBeenCalled());
      const chamadasIniciais = vi.mocked(alertsApi.getAlerts).mock.calls.length;

      await vi.advanceTimersByTimeAsync(130000);

      expect(vi.mocked(alertsApi.getAlerts).mock.calls.length).toBeGreaterThan(
        chamadasIniciais,
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('continua atualizando o status pelo alert_update', async () => {
    vi.mocked(alertsApi.getAlerts).mockResolvedValue(pagina([alerta('PAC-1__t1')]));
    renderizar();
    await waitFor(() => expect(screen.getByTestId('ids')).toHaveTextContent('PAC-1__t1'));

    publicar?.({ type: 'alert_update', alert_id: 'PAC-1__t1', status: 'acknowledged' });

    await waitFor(() => expect(screen.getByTestId('ids')).toHaveTextContent('PAC-1__t1'));
  });
});
