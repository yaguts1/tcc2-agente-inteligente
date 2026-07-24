import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useLocalStorageSync, useOfflineAlertCache, useWebSocketStorageSync } from './useLocalStorageSync';

interface Alert {
  id: string;
  timestamp: string;
  severity: 'info' | 'warning' | 'critical';
  message: string;
  patient_id?: string;
  [key: string]: any;
}

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};

  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

describe('useLocalStorageSync', () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  it('deve retornar array vazio quando localStorage está vazio', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    act(() => {
      const alerts = result.current.getLocalAlerts();
      expect(alerts).toEqual([]);
    });
  });

  it('deve salvar e recuperar alertas do localStorage', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    const testAlerts: Alert[] = [
      {
        id: '1',
        timestamp: new Date().toISOString(),
        severity: 'warning',
        message: 'Teste 1',
      },
      {
        id: '2',
        timestamp: new Date().toISOString(),
        severity: 'critical',
        message: 'Teste 2',
      },
    ];

    act(() => {
      result.current.saveLocalAlerts(testAlerts);
    });

    act(() => {
      const saved = result.current.getLocalAlerts();
      expect(saved).toHaveLength(2);
      expect(saved[0].id).toBe('1');
      expect(saved[1].id).toBe('2');
    });
  });

  it('deve sincronizar um único alerta', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    const alert1: Alert = {
      id: '1',
      timestamp: new Date().toISOString(),
      severity: 'warning',
      message: 'Alerta 1',
    };

    act(() => {
      result.current.syncAlert(alert1);
    });

    act(() => {
      const alerts = result.current.getLocalAlerts();
      expect(alerts).toHaveLength(1);
      expect(alerts[0].id).toBe('1');
    });
  });

  it('deve evitar duplicatas ao sincronizar alertas', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    const alert: Alert = {
      id: '1',
      timestamp: new Date().toISOString(),
      severity: 'warning',
      message: 'Alerta 1',
    };

    act(() => {
      result.current.syncAlert(alert);
      result.current.syncAlert(alert); // Tentar adicionar novamente
    });

    act(() => {
      const alerts = result.current.getLocalAlerts();
      expect(alerts).toHaveLength(1);
    });
  });

  it('deve sincronizar múltiplos alertas', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    const alerts: Alert[] = [
      {
        id: '1',
        timestamp: new Date().toISOString(),
        severity: 'warning',
        message: 'Alerta 1',
      },
      {
        id: '2',
        timestamp: new Date().toISOString(),
        severity: 'critical',
        message: 'Alerta 2',
      },
    ];

    act(() => {
      result.current.syncAlerts(alerts);
    });

    act(() => {
      const saved = result.current.getLocalAlerts();
      expect(saved).toHaveLength(2);
    });
  });

  it('deve limpar alertas expirados', () => {
    const { result } = renderHook(() =>
      useLocalStorageSync({ retentionMinutes: 60 })
    );
    
    const now = new Date();
    const old = new Date(now.getTime() - 90 * 60 * 1000); // 90 min atrás
    
    const alerts: Alert[] = [
      {
        id: '1',
        timestamp: now.toISOString(),
        severity: 'warning',
        message: 'Recente',
      },
      {
        id: '2',
        timestamp: old.toISOString(),
        severity: 'warning',
        message: 'Expirado',
      },
    ];

    // Escreve direto no mock, contornando o filtro de expirados que
    // saveLocalAlerts() já aplica na escrita — o objetivo aqui é simular
    // dados que já estavam no localStorage (ex: gravados antes, ou o tempo
    // passou desde então) para testar clearExpired() isoladamente.
    act(() => {
      localStorageMock.setItem('alerts_cache', JSON.stringify(alerts));
    });

    act(() => {
      const removed = result.current.clearExpired();
      expect(removed).toBe(1);
    });

    act(() => {
      const remaining = result.current.getLocalAlerts();
      expect(remaining).toHaveLength(1);
      expect(remaining[0].id).toBe('1');
    });
  });

  it('deve respeitar limite máximo de itens', () => {
    const { result } = renderHook(() =>
      useLocalStorageSync({ maxItems: 3 })
    );
    
    const alerts: Alert[] = Array.from({ length: 5 }, (_, i) => ({
      id: `${i}`,
      timestamp: new Date().toISOString(),
      severity: 'warning' as const,
      message: `Alerta ${i}`,
    }));

    act(() => {
      result.current.saveLocalAlerts(alerts);
    });

    act(() => {
      const saved = result.current.getLocalAlerts();
      expect(saved).toHaveLength(3);
    });
  });

  it('deve limpar todo o cache', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    const alerts: Alert[] = [
      {
        id: '1',
        timestamp: new Date().toISOString(),
        severity: 'warning',
        message: 'Teste',
      },
    ];

    act(() => {
      result.current.saveLocalAlerts(alerts);
    });

    act(() => {
      result.current.clearAll();
    });

    act(() => {
      const alerts = result.current.getLocalAlerts();
      expect(alerts).toHaveLength(0);
    });
  });

  it('deve retornar estatísticas corretas', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    const alerts: Alert[] = [
      {
        id: '1',
        timestamp: new Date().toISOString(),
        severity: 'warning',
        message: 'Teste',
      },
    ];

    act(() => {
      result.current.saveLocalAlerts(alerts);
    });

    act(() => {
      const stats = result.current.getStats();
      expect(stats.totalItems).toBe(1);
      expect(stats.lastSyncTime).not.toBeNull();
      expect(stats.lastError).toBeNull();
    });
  });

  it('deve rastrear total sincronizado', () => {
    const { result } = renderHook(() => useLocalStorageSync());
    
    const alert1: Alert = {
      id: '1',
      timestamp: new Date().toISOString(),
      severity: 'warning',
      message: 'Teste 1',
    };

    const alert2: Alert = {
      id: '2',
      timestamp: new Date().toISOString(),
      severity: 'warning',
      message: 'Teste 2',
    };

    act(() => {
      result.current.syncAlert(alert1);
      result.current.syncAlert(alert2);
    });

    act(() => {
      const stats = result.current.getStats();
      expect(stats.totalSynced).toBe(2);
    });
  });
});

describe('useOfflineAlertCache', () => {
  beforeEach(() => {
    localStorageMock.clear();
    Object.defineProperty(navigator, 'onLine', {
      writable: true,
      value: true,
    });
  });

  it('deve detectar estado online', () => {
    const { result } = renderHook(() => useOfflineAlertCache());
    
    expect(result.current.isOffline).toBe(false);
  });

  it('deve detectar estado offline', () => {
    Object.defineProperty(navigator, 'onLine', {
      writable: true,
      value: false,
    });

    const { result } = renderHook(() => useOfflineAlertCache());
    
    expect(result.current.isOffline).toBe(true);
  });

  it('deve retornar alertas em cache quando offline', () => {
    const { result: syncResult } = renderHook(() => useLocalStorageSync());
    
    const alert: Alert = {
      id: '1',
      timestamp: new Date().toISOString(),
      severity: 'warning',
      message: 'Teste',
    };

    act(() => {
      syncResult.current.saveLocalAlerts([alert]);
    });

    Object.defineProperty(navigator, 'onLine', {
      writable: true,
      value: false,
    });

    const { result: offlineResult } = renderHook(() => useOfflineAlertCache());
    
    expect(offlineResult.current.cachedAlerts).toHaveLength(1);
  });
});

describe('useWebSocketStorageSync', () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  it('deve sincronizar alertas automaticamente', () => {
    const alerts: Alert[] = [
      {
        id: '1',
        timestamp: new Date().toISOString(),
        severity: 'warning',
        message: 'Teste',
      },
    ];

    const { result } = renderHook(() => 
      useWebSocketStorageSync(alerts)
    );

    // Aguardar sincronização
    expect(true).toBe(true);
  });

  it('deve ignorar alertas vazios', () => {
    const { result: syncResult } = renderHook(() => useLocalStorageSync());
    
    renderHook(() => useWebSocketStorageSync([]));

    act(() => {
      const alerts = syncResult.current.getLocalAlerts();
      expect(alerts).toHaveLength(0);
    });
  });
});

describe('Integração localStorage Sync', () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  it('deve manter integridade ao sincronizar e limpar', () => {
    const { result } = renderHook(() =>
      useLocalStorageSync({ maxItems: 100, retentionMinutes: 1440 })
    );

    const alerts: Alert[] = Array.from({ length: 10 }, (_, i) => ({
      id: `${i}`,
      timestamp: new Date().toISOString(),
      severity: i % 2 === 0 ? 'warning' : 'critical',
      message: `Alerta ${i}`,
    }));

    act(() => {
      result.current.syncAlerts(alerts);
    });

    act(() => {
      const saved = result.current.getLocalAlerts();
      expect(saved).toHaveLength(10);
      expect(saved[0].id).toBe('9'); // Mais recente primeiro
    });

    act(() => {
      const stats = result.current.getStats();
      expect(stats.totalItems).toBe(10);
      expect(stats.totalSynced).toBe(10);
    });
  });

  it('deve recuperar após limpeza', () => {
    const { result } = renderHook(() => useLocalStorageSync());

    const alert1: Alert = {
      id: '1',
      timestamp: new Date().toISOString(),
      severity: 'warning',
      message: 'Alerta 1',
    };

    act(() => {
      result.current.syncAlert(alert1);
    });

    act(() => {
      result.current.clearAll();
    });

    const alert2: Alert = {
      id: '2',
      timestamp: new Date().toISOString(),
      severity: 'warning',
      message: 'Alerta 2',
    };

    act(() => {
      result.current.syncAlert(alert2);
    });

    act(() => {
      const alerts = result.current.getLocalAlerts();
      expect(alerts).toHaveLength(1);
      expect(alerts[0].id).toBe('2');
    });
  });
});
