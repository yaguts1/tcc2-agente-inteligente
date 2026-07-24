import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePolling } from './usePolling';

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('chama onPoll a cada intervalo enquanto enabled', () => {
    const onPoll = vi.fn();
    renderHook(() => usePolling({ interval: 1000, enabled: true, onPoll }));

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(onPoll).toHaveBeenCalledTimes(3);
  });

  it('PARA o polling quando a prop enabled muda para false (regressão)', () => {
    // Antes, isPolling só era semeado de enabled na montagem; mudar a prop
    // (ex: enabled={!wsConnected}) não parava o polling.
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ enabled }) => usePolling({ interval: 1000, enabled, onPoll }),
      { initialProps: { enabled: true } },
    );

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onPoll).toHaveBeenCalledTimes(2);

    act(() => {
      rerender({ enabled: false });
    });
    onPoll.mockClear();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onPoll).not.toHaveBeenCalled(); // polling parou de fato
  });

  it('RETOMA o polling quando enabled volta para true', () => {
    const onPoll = vi.fn();
    const { rerender } = renderHook(
      ({ enabled }) => usePolling({ interval: 1000, enabled, onPoll }),
      { initialProps: { enabled: false } },
    );

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(onPoll).not.toHaveBeenCalled();

    act(() => {
      rerender({ enabled: true });
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onPoll).toHaveBeenCalledTimes(2);
  });
});
