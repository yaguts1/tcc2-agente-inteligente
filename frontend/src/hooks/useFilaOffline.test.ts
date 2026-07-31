/**
 * O dreno da fila.
 *
 * A distinção que este arquivo protege é a única decisão difícil de 4.7:
 * **falha de rede reenvia, recusa do servidor descarta.**
 *
 * Errar para um lado (reenviar sempre) cria pendência imortal — um alerta que
 * outra pessoa já fechou falharia com 409 para sempre, o indicador nunca
 * zeraria, e um indicador que nunca zera é ignorado, o que o inutiliza
 * justamente para o caso real.
 *
 * Errar para o outro (descartar sempre) reproduz o defeito original: a ação
 * some no corredor e a pessoa não sabe.
 */
import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

const acknowledge = vi.fn();
const complete = vi.fn();

vi.mock('../lib/api', async () => {
  const real = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...real,
    alertsApi: { acknowledge, complete },
  };
});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const { ApiException } = await import('../lib/api');
const { enfileirar, limpar, listar } = await import('../lib/filaOffline');
const { useFilaOffline } = await import('./useFilaOffline');

beforeEach(async () => {
  await limpar();
  acknowledge.mockReset();
  complete.mockReset();
});

describe('dreno', () => {
  it('envia as pendentes e esvazia a fila', async () => {
    await enfileirar({ tipo: 'acknowledge', alertId: 'A' });
    await enfileirar({ tipo: 'complete', alertId: 'B', motivo: 'reposicionado' });
    acknowledge.mockResolvedValue(undefined);
    complete.mockResolvedValue(undefined);

    const { result } = renderHook(() => useFilaOffline());
    await act(async () => {
      await result.current.drenar();
    });

    expect(acknowledge).toHaveBeenCalledWith('A');
    expect(complete).toHaveBeenCalledWith('B', 'reposicionado');
    await waitFor(async () => expect(await listar()).toHaveLength(0));
  });

  it('falha de REDE mantém a ação na fila', async () => {
    // O caso que a fila existe para cobrir: o pedido não chegou, e vale.
    await enfileirar({ tipo: 'acknowledge', alertId: 'A' });
    acknowledge.mockRejectedValue(new TypeError('Failed to fetch'));

    const { result } = renderHook(() => useFilaOffline());
    await act(async () => {
      await result.current.drenar();
    });

    const fila = await listar();
    expect(fila).toHaveLength(1);
    expect(fila[0].tentativas).toBe(1);
  });

  it('recusa do SERVIDOR descarta a ação', async () => {
    // 409 significa que o pedido chegou e não vale — outra pessoa já fechou o
    // alerta. Repetir não muda a resposta, e a entrada ficaria imortal.
    await enfileirar({ tipo: 'complete', alertId: 'A' });
    complete.mockRejectedValue(new ApiException('conflito', 409));

    const { result } = renderHook(() => useFilaOffline());
    await act(async () => {
      await result.current.drenar();
    });

    expect(await listar()).toHaveLength(0);
  });

  it('erro 5xx é REENVIADO, mas com teto', async () => {
    // Diferente do 4xx: 500 pode melhorar com repetição, porque o servidor pode
    // voltar — descartar imediatamente perderia uma ação válida por causa de um
    // deploy. Mas também não pode insistir para sempre, e é o
    // `MAX_TENTATIVAS` que fecha isso.
    await enfileirar({ tipo: 'acknowledge', alertId: 'A' });
    acknowledge.mockRejectedValue(new ApiException('erro', 500));

    const { result } = renderHook(() => useFilaOffline());
    await act(async () => {
      await result.current.drenar();
    });

    const fila = await listar();
    expect(fila).toHaveLength(1);
    expect(fila[0].tentativas).toBe(1);
  });

  it('para no primeiro erro de rede em vez de queimar as seguintes', async () => {
    // Continuar tentando as próximas só gastaria tempo — elas vão falhar
    // igual — e a ordem importa: é a ordem em que a pessoa agiu.
    await enfileirar({ tipo: 'acknowledge', alertId: 'A' });
    await enfileirar({ tipo: 'acknowledge', alertId: 'B' });
    acknowledge.mockRejectedValue(new TypeError('Failed to fetch'));

    const { result } = renderHook(() => useFilaOffline());
    await act(async () => {
      await result.current.drenar();
    });

    expect(acknowledge).toHaveBeenCalledTimes(1);
    expect(await listar()).toHaveLength(2);
  });

  it('avisa quando sincroniza, para a pessoa não refazer', async () => {
    const aoSincronizar = vi.fn();
    await enfileirar({ tipo: 'acknowledge', alertId: 'A' });
    acknowledge.mockResolvedValue(undefined);

    const { result } = renderHook(() => useFilaOffline(aoSincronizar));
    await act(async () => {
      await result.current.drenar();
    });

    // Recarregar a lista depois de sincronizar: sem isso a tela fica com o
    // estado otimista e a divergência só aparece no próximo polling.
    expect(aoSincronizar).toHaveBeenCalled();
  });

  it('expõe as pendentes para a tela poder mostrá-las', async () => {
    // Uma fila que reenvia em silêncio resolve metade do problema. A pessoa
    // ainda não sabe se o que fez chegou, e na dúvida refaz ou anota no papel.
    await enfileirar({ tipo: 'acknowledge', alertId: 'A' });

    const { result } = renderHook(() => useFilaOffline());

    await waitFor(() => expect(result.current.pendentes).toHaveLength(1));
  });
});
