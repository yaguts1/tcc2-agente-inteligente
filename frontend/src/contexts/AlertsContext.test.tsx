/**
 * Fluxo de alertas — o núcleo do produto.
 *
 * Reconhecer e concluir um alerta de reposicionamento é a ação que o sistema
 * existe para apoiar, e não havia UM teste cobrindo isso: a suíte do frontend
 * tinha 3 casos, todos sobre polling e localStorage.
 *
 * O caso mais importante aqui é o de FALHA na busca. Num monitor de leito, uma
 * lista desatualizada exibida como se fosse atual é pior do que uma tela de
 * erro: a enfermeira toma decisão sobre dado velho sem saber que é velho.
 */
import { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AlertsProvider, useAlerts } from './AlertsContext';
import { ApiException } from '../lib/api';
import type { Alert, PaginaDeAlertas } from '../lib/api';

vi.mock('../lib/api', async () => {
  const real = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...real,
    alertsApi: {
      getAlerts: vi.fn(),
      acknowledge: vi.fn(),
      complete: vi.fn(),
    },
  };
});

// O contexto de WebSocket é irrelevante aqui: queremos o caminho HTTP.
// Reportar "desconectado" mantém o polling ligado, como em produção quando o
// WS cai.
vi.mock('./WebSocketContext', () => ({
  useWebSocketContext: () => ({ isConnected: false, subscribe: () => () => {} }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { alertsApi } from '../lib/api';
import { toast } from 'sonner';

const alertaExemplo = {
  id: 'PAC-0001__2026-01-01T10:00:00',
  patientName: 'Maria Silva',
  room: '101',
  bed: 'A',
  lastRepositioning: '2026-01-01T08:00:00',
  nextRepositioning: '2026-01-01T10:00:00',
  riskLevel: 'high' as const,
  status: 'pending' as const,
};

/** Componente sonda: expõe o estado do contexto como texto verificável. */
function Sonda() {
  const { alerts, error, isOffline, acknowledgeAlert, completeAlert } = useAlerts();
  return (
    <div>
      <span data-testid="erro">{error ?? ''}</span>
      <span data-testid="offline">{String(isOffline)}</span>
      <ul>
        {alerts.map((a) => (
          <li key={a.id} data-testid="alerta">
            {a.patientName}:{a.status}
          </li>
        ))}
      </ul>
      <button onClick={() => acknowledgeAlert(alertaExemplo.id).catch(() => {})}>
        reconhecer
      </button>
      <button onClick={() => completeAlert(alertaExemplo.id).catch(() => {})}>
        concluir
      </button>
    </div>
  );
}


// A API devolve a página (itens + total) para que o truncamento seja visível.
// Nos testes o total é sempre o tamanho da lista: nada truncado.
const pagina = (itens: Alert[]): PaginaDeAlertas => ({
  itens,
  total: itens.length,
  truncado: false,
});

const renderizar = (children: ReactNode = <Sonda />) =>
  render(<AlertsProvider>{children}</AlertsProvider>);

beforeEach(() => {
  vi.mocked(alertsApi.getAlerts).mockResolvedValue(pagina([alertaExemplo]));
  vi.mocked(alertsApi.acknowledge).mockResolvedValue(undefined as never);
  vi.mocked(alertsApi.complete).mockResolvedValue(undefined as never);
});

describe('carga inicial', () => {
  it('exibe os alertas retornados pela API', async () => {
    renderizar();
    expect(await screen.findByTestId('alerta')).toHaveTextContent('Maria Silva:pending');
  });
});

describe('falha ao buscar alertas', () => {
  it('informa o usuário em vez de falhar em silêncio', async () => {
    vi.mocked(alertsApi.getAlerts).mockRejectedValue(
      new ApiException('Erro interno ao processar a requisição.', 500),
    );

    renderizar();

    await waitFor(() => {
      // A mensagem do servidor precisa chegar ao usuário: um aviso genérico
      // não permite distinguir "backend caiu" de "sessão expirou".
      expect(screen.getByTestId('erro')).toHaveTextContent(
        'Erro interno ao processar a requisição.',
      );
    });
  });

  it('não apresenta lista vazia como se fosse "nenhum alerta"', async () => {
    // Primeira carga funciona; a seguinte falha (backend caiu no meio do uso).
    vi.mocked(alertsApi.getAlerts)
      .mockResolvedValueOnce(pagina([alertaExemplo]))
      .mockRejectedValue(new ApiException('falhou', 500));

    renderizar();
    await screen.findByTestId('alerta');

    // Força uma nova busca por uma ação que falha depois.
    vi.mocked(alertsApi.acknowledge).mockRejectedValue(new ApiException('falhou', 500));
    await userEvent.click(screen.getByRole('button', { name: 'reconhecer' }));

    await waitFor(() => {
      expect(screen.getByTestId('erro')).toHaveTextContent(/Falha ao atualizar alertas/);
    });
    // E o alerta carregado antes CONTINUA na tela: apagá-lo mostraria
    // "nenhum alerta", que é exatamente a leitura errada.
    expect(screen.getByTestId('alerta')).toBeInTheDocument();
  });

  it('marca offline quando o navegador está sem rede', async () => {
    const spy = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    vi.mocked(alertsApi.getAlerts).mockRejectedValue(new TypeError('Failed to fetch'));

    renderizar();

    await waitFor(() => {
      expect(screen.getByTestId('offline')).toHaveTextContent('true');
    });
    spy.mockRestore();
  });
});

describe('reconhecer alerta', () => {
  it('chama a API e reflete o novo status', async () => {
    renderizar();
    await screen.findByTestId('alerta');

    await userEvent.click(screen.getByRole('button', { name: 'reconhecer' }));

    expect(alertsApi.acknowledge).toHaveBeenCalledWith(alertaExemplo.id);
    await waitFor(() => {
      expect(screen.getByTestId('alerta')).toHaveTextContent('acknowledged');
    });
  });

  it('desfaz a atualização otimista quando a API falha', async () => {
    vi.mocked(alertsApi.acknowledge).mockRejectedValue(new ApiException('falhou', 500));
    renderizar();
    await screen.findByTestId('alerta');

    await userEvent.click(screen.getByRole('button', { name: 'reconhecer' }));

    // A releitura devolve o estado real do servidor: continua pendente. Sem
    // isso a tela mostraria "reconhecido" para uma ação que não foi gravada.
    await waitFor(() => {
      expect(screen.getByTestId('alerta')).toHaveTextContent('pending');
    });
    expect(toast.error).toHaveBeenCalled();
  });
});

describe('concluir alerta', () => {
  it('chama a API e reflete o novo status', async () => {
    renderizar();
    await screen.findByTestId('alerta');

    await userEvent.click(screen.getByRole('button', { name: 'concluir' }));

    expect(alertsApi.complete).toHaveBeenCalledWith(alertaExemplo.id);
    await waitFor(() => {
      expect(screen.getByTestId('alerta')).toHaveTextContent('completed');
    });
  });

  it('avisa e não marca como concluído quando a API falha', async () => {
    vi.mocked(alertsApi.complete).mockRejectedValue(new ApiException('falhou', 500));
    renderizar();
    await screen.findByTestId('alerta');

    await userEvent.click(screen.getByRole('button', { name: 'concluir' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
    expect(screen.getByTestId('alerta')).toHaveTextContent('pending');
  });
});
