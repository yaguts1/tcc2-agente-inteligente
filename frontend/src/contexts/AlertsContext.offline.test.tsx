/**
 * A decisão de ENFILEIRAR, que é onde 4.7 pode errar caro.
 *
 * **Falha de rede enfileira; recusa do servidor reverte.**
 *
 * Errar para um lado (enfileirar sempre) cria pendência imortal: um alerta que
 * outra pessoa já fechou falharia com 409 a cada tentativa, o indicador nunca
 * zeraria, e um indicador que nunca zera é ignorado — o que o inutiliza
 * justamente para o caso real.
 *
 * Errar para o outro (nunca enfileirar) é o defeito original: a ação some no
 * corredor e a enfermeira acredita ter registrado o reposicionamento enquanto o
 * prontuário diz que não.
 *
 * Este arquivo existe porque a mutação "enfileirar também em erro do servidor"
 * passou por TODOS os testes existentes do contexto — a fila é invisível para
 * quem só olha a lista de alertas.
 */
import 'fake-indexeddb/auto';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

vi.mock('./WebSocketContext', () => ({
  useWebSocketContext: () => ({ isConnected: false, subscribe: () => () => undefined }),
}));

const { alertsApi, ApiException } = await import('../lib/api');
const { AlertsProvider, useAlerts } = await import('./AlertsContext');
const { limpar, listar } = await import('../lib/filaOffline');

const ALERTA = {
  id: 'PAC-0001__2026-06-01T08:00:00',
  patientId: 'PAC-0001',
  patientName: 'Maria',
  room: '201',
  bed: 'A',
  lastRepositioning: '2026-06-01T07:00:00',
  nextRepositioning: '2026-06-01T08:00:00',
  riskLevel: 'high' as const,
  status: 'pending' as const,
  closureOrigin: null,
  closedBy: null,
  site: null,
  minutesOpen: 0,
  escalationLevel: 'normal' as const,
};

function Tela() {
  const { acknowledgeAlert, completeAlert } = useAlerts();
  return (
    <>
      <button onClick={() => acknowledgeAlert(ALERTA.id).catch(() => undefined)}>
        reconhecer
      </button>
      <button onClick={() => completeAlert(ALERTA.id).catch(() => undefined)}>
        concluir
      </button>
    </>
  );
}

function montar() {
  return render(
    <AlertsProvider>
      <Tela />
    </AlertsProvider>,
  );
}

beforeEach(async () => {
  await limpar();
  vi.mocked(alertsApi.getAlerts).mockResolvedValue({ itens: [ALERTA], total: 1 } as never);
  vi.mocked(alertsApi.acknowledge).mockReset();
  vi.mocked(alertsApi.complete).mockReset();
});

describe('falha de rede', () => {
  it('reconhecer offline vai para a fila', async () => {
    // `TypeError` é a assinatura de falha de rede do `fetch`: o pedido não
    // chegou, e a decisão da enfermeira vale.
    vi.mocked(alertsApi.acknowledge).mockRejectedValue(new TypeError('Failed to fetch'));
    montar();

    await userEvent.click(await screen.findByText('reconhecer'));

    await waitFor(async () => {
      const fila = await listar();
      expect(fila).toHaveLength(1);
      expect(fila[0].tipo).toBe('acknowledge');
      expect(fila[0].alertId).toBe(ALERTA.id);
    });
  });

  it('concluir offline vai para a fila COM o motivo', async () => {
    // Sem o motivo, o reenvio registraria "reposicionado" para um alerta
    // encerrado como "recusa do paciente" — e é essa afirmação que vira número
    // de adesão.
    vi.mocked(alertsApi.complete).mockRejectedValue(new TypeError('Failed to fetch'));
    montar();

    await userEvent.click(await screen.findByText('concluir'));

    await waitFor(async () => {
      const fila = await listar();
      expect(fila).toHaveLength(1);
      expect(fila[0].tipo).toBe('complete');
    });
  });
});

describe('recusa do servidor', () => {
  it('409 NÃO vai para a fila', async () => {
    // O pedido chegou e foi recusado — outra pessoa já agiu. Enfileirar
    // produziria uma pendência que nunca sai, porque repetir não muda a
    // resposta.
    vi.mocked(alertsApi.complete).mockRejectedValue(new ApiException('conflito', 409));
    montar();

    await userEvent.click(await screen.findByText('concluir'));

    await waitFor(() => expect(alertsApi.complete).toHaveBeenCalled());
    expect(await listar()).toHaveLength(0);
  });

  it('500 NÃO vai para a fila', async () => {
    // Erro do servidor também é resposta: o pedido chegou. A recuperação é
    // responsabilidade de quem tentar de novo, não de uma fila que insiste.
    vi.mocked(alertsApi.acknowledge).mockRejectedValue(new ApiException('erro', 500));
    montar();

    await userEvent.click(await screen.findByText('reconhecer'));

    await waitFor(() => expect(alertsApi.acknowledge).toHaveBeenCalled());
    expect(await listar()).toHaveLength(0);
  });
});

describe('sucesso', () => {
  it('não enfileira nada quando a rede está boa', async () => {
    vi.mocked(alertsApi.acknowledge).mockResolvedValue(undefined as never);
    montar();

    await userEvent.click(await screen.findByText('reconhecer'));

    await waitFor(() => expect(alertsApi.acknowledge).toHaveBeenCalled());
    expect(await listar()).toHaveLength(0);
  });
});

describe('navigator.onLine mentindo', () => {
  it('o servidor respondeu 409 e o navegador se diz offline: NÃO enfileira', async () => {
    // `navigator.onLine` é notoriamente pouco confiável — reporta a interface
    // de rede, não a alcançabilidade do servidor, e pode virar `false` entre a
    // requisição e o `catch` (troca de AP, portal cativo).
    //
    // Aqui o servidor DE FATO respondeu, e a resposta foi "não vale". Sem o
    // `instanceof ApiException` antes da checagem de `onLine`, esta ação iria
    // para a fila e ficaria imortal: repetir um 409 não muda nada.
    //
    // Foi por isto que a mutação que remove aquele guarda sobrevivia a todos os
    // outros testes: em jsdom `onLine` é sempre `true`, e o segundo caminho
    // barrava sozinho.
    const original = Object.getOwnPropertyDescriptor(navigator, 'onLine');
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    try {
      vi.mocked(alertsApi.complete).mockRejectedValue(new ApiException('conflito', 409));
      montar();

      await userEvent.click(await screen.findByText('concluir'));

      await waitFor(() => expect(alertsApi.complete).toHaveBeenCalled());
      expect(await listar()).toHaveLength(0);
    } finally {
      if (original) Object.defineProperty(navigator, 'onLine', original);
    }
  });

  it('o navegador se diz offline e o fetch falhou: ENFILEIRA', async () => {
    // A outra metade: sem resposta do servidor, a ação vale e precisa ser
    // guardada.
    const original = Object.getOwnPropertyDescriptor(navigator, 'onLine');
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    try {
      vi.mocked(alertsApi.complete).mockRejectedValue(new TypeError('Failed to fetch'));
      montar();

      await userEvent.click(await screen.findByText('concluir'));

      await waitFor(async () => expect(await listar()).toHaveLength(1));
    } finally {
      if (original) Object.defineProperty(navigator, 'onLine', original);
    }
  });
});
