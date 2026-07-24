import { useEffect, useCallback, useRef, useState } from 'react';

interface Alert {
  id: string;
  timestamp: string;
  severity: 'info' | 'warning' | 'critical';
  message: string;
  patient_id?: string;
  [key: string]: any;
}

interface LocalStorageSyncConfig {
  storageKey?: string;
  maxItems?: number;
  retentionMinutes?: number;
  autoSync?: boolean;
}

interface SyncStats {
  lastSyncTime: Date | null;
  totalItems: number;
  totalSynced: number;
  lastError: string | null;
}

const DEFAULT_CONFIG: Required<LocalStorageSyncConfig> = {
  storageKey: 'alerts_cache',
  maxItems: 1000,
  retentionMinutes: 24 * 60, // 24 horas
  autoSync: true,
};

/**
 * Hook para sincronizar alertas com localStorage
 * Permite acesso offline a alertas recentes
 */
export function useLocalStorageSync(config: LocalStorageSyncConfig = {}) {
  const finalConfig = { ...DEFAULT_CONFIG, ...config };
  const [stats, setStats] = useState<SyncStats>({
    lastSyncTime: null,
    totalItems: 0,
    totalSynced: 0,
    lastError: null,
  });
  const syncInProgressRef = useRef(false);

  /**
   * Retorna alertas do localStorage
   */
  const getLocalAlerts = useCallback((): Alert[] => {
    try {
      const stored = localStorage.getItem(finalConfig.storageKey);
      if (!stored) return [];

      const data = JSON.parse(stored);
      if (!Array.isArray(data)) return [];

      console.debug(`[localStorage] Lidos ${data.length} alertas`);
      return data;
    } catch (error) {
      console.error('[localStorage] Erro ao ler:', error);
      setStats(prev => ({
        ...prev,
        lastError: `Erro ao ler localStorage: ${error}`,
      }));
      return [];
    }
  }, [finalConfig.storageKey]);

  /**
   * Salva alertas no localStorage
   * Remove alertas expirados e mantém limite máximo
   */
  const saveLocalAlerts = useCallback((alerts: Alert[]): void => {
    try {
      const now = new Date().getTime();
      const retentionMs = finalConfig.retentionMinutes * 60 * 1000;

      // Filtrar alertas válidos (não expirados)
      const validAlerts = alerts.filter((alert) => {
        const alertTime = new Date(alert.timestamp).getTime();
        return now - alertTime < retentionMs;
      });

      // Limitar quantidade máxima
      const trimmedAlerts = validAlerts.slice(0, finalConfig.maxItems);

      // Salvar no localStorage
      localStorage.setItem(finalConfig.storageKey, JSON.stringify(trimmedAlerts));

      console.info(`[localStorage] Salvos ${trimmedAlerts.length}/${finalConfig.maxItems} alertas`);

      setStats(prev => ({
        ...prev,
        totalItems: trimmedAlerts.length,
        lastSyncTime: new Date(),
        lastError: null,
      }));
    } catch (error) {
      console.error('[localStorage] Erro ao salvar:', error);
      setStats(prev => ({
        ...prev,
        lastError: `Erro ao salvar localStorage: ${error}`,
      }));
    }
  }, [finalConfig.maxItems, finalConfig.retentionMinutes, finalConfig.storageKey]);

  /**
   * Sincroniza um alerta recebido via WebSocket com localStorage
   */
  const syncAlert = useCallback((alert: Alert): void => {
    try {
      const current = getLocalAlerts();
      
      // Verificar se alerta já existe (por ID ou timestamp)
      const exists = current.some(
        a => a.id === alert.id || 
             (new Date(a.timestamp).getTime() === new Date(alert.timestamp).getTime())
      );

      if (!exists) {
        const updated = [alert, ...current];
        saveLocalAlerts(updated);

        setStats(prev => ({
          ...prev,
          totalSynced: prev.totalSynced + 1,
        }));

        console.debug(`[localStorage] Alerta sincronizado: ${alert.id}`);
      }
    } catch (error) {
      console.error('[localStorage] Erro ao sincronizar alerta:', error);
    }
  }, [getLocalAlerts, saveLocalAlerts]);

  /**
   * Sincroniza múltiplos alertas
   */
  const syncAlerts = useCallback((alerts: Alert[]): void => {
    if (syncInProgressRef.current) {
      console.warn('[localStorage] Sync já em progresso');
      return;
    }

    syncInProgressRef.current = true;
    try {
      const current = getLocalAlerts();
      const existingIds = new Set(current.map(a => a.id));

      // Adicionar novos alertas (evitar duplicatas)
      const newAlerts = alerts.filter(a => !existingIds.has(a.id));
      const merged = [...newAlerts, ...current];

      saveLocalAlerts(merged);

      setStats(prev => ({
        ...prev,
        totalSynced: prev.totalSynced + newAlerts.length,
      }));

      console.info(`[localStorage] ${newAlerts.length} alertas sincronizados`);
    } catch (error) {
      console.error('[localStorage] Erro ao sincronizar alertas:', error);
    } finally {
      syncInProgressRef.current = false;
    }
  }, [getLocalAlerts, saveLocalAlerts]);

  /**
   * Limpa alertas expirados do localStorage
   */
  const clearExpired = useCallback((): number => {
    try {
      const current = getLocalAlerts();
      const now = new Date().getTime();
      const retentionMs = finalConfig.retentionMinutes * 60 * 1000;

      const validAlerts = current.filter((alert) => {
        const alertTime = new Date(alert.timestamp).getTime();
        return now - alertTime < retentionMs;
      });

      const removed = current.length - validAlerts.length;
      if (removed > 0) {
        saveLocalAlerts(validAlerts);
        console.info(`[localStorage] ${removed} alertas expirados removidos`);
      }

      return removed;
    } catch (error) {
      console.error('[localStorage] Erro ao limpar expirados:', error);
      return 0;
    }
  }, [getLocalAlerts, saveLocalAlerts, finalConfig.retentionMinutes]);

  /**
   * Limpa todo o cache
   */
  const clearAll = useCallback((): void => {
    try {
      localStorage.removeItem(finalConfig.storageKey);
      setStats({
        lastSyncTime: new Date(),
        totalItems: 0,
        totalSynced: 0,
        lastError: null,
      });
      console.info('[localStorage] Cache limpo completamente');
    } catch (error) {
      console.error('[localStorage] Erro ao limpar cache:', error);
    }
  }, [finalConfig.storageKey]);

  /**
   * Retorna estatísticas de sincronização
   */
  const getStats = useCallback((): SyncStats => {
    return {
      ...stats,
      totalItems: getLocalAlerts().length,
    };
  }, [stats, getLocalAlerts]);

  /**
   * Setup: Limpar alertas expirados periodicamente
   */
  useEffect(() => {
    if (!finalConfig.autoSync) return;

    // Limpar expirados a cada 10 minutos
    const interval = setInterval(() => {
      clearExpired();
    }, 10 * 60 * 1000);

    console.info('[localStorage] Limpeza periódica iniciada (a cada 10 min)');

    return () => {
      clearInterval(interval);
      console.info('[localStorage] Limpeza periódica finalizada');
    };
  }, [finalConfig.autoSync, clearExpired]);

  return {
    // Métodos
    getLocalAlerts,
    syncAlert,
    syncAlerts,
    clearExpired,
    clearAll,
    getStats,
    saveLocalAlerts,

    // Estado
    stats,
  };
}

/**
 * Hook auxiliar para sincronização automática com WebSocket
 */
export function useWebSocketStorageSync(
  alerts: Alert[],
  config: LocalStorageSyncConfig = {}
) {
  const { syncAlerts } = useLocalStorageSync(config);

  useEffect(() => {
    if (alerts && alerts.length > 0) {
      syncAlerts(alerts);
    }
  }, [alerts, syncAlerts]);
}

/**
 * Hook para restaurar alertas do cache offline
 */
export function useOfflineAlertCache(config: LocalStorageSyncConfig = {}) {
  const { getLocalAlerts, clearAll } = useLocalStorageSync(config);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const handleOnline = () => {
      setIsOffline(false);
      console.info('[offline] Browser online detectado');
    };

    const handleOffline = () => {
      setIsOffline(true);
      console.warn('[offline] Browser offline detectado');
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return {
    isOffline,
    cachedAlerts: isOffline ? getLocalAlerts() : [],
    clearCache: clearAll,
  };
}
