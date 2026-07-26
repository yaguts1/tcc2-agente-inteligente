import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { alertsApi, Alert, ApiException } from '../lib/api';
import { useWebSocketContext } from './WebSocketContext';
import { usePolling } from '../hooks/usePolling';
import { useCriticalAlerts, CriticalAlert } from '../hooks/useCriticalAlerts';
import { toast } from 'sonner';

interface CriticalAlertsData {
  criticalAlerts: CriticalAlert[];
  totalCritical: number;
  highRisk: number;
  acknowledgedMedium: number;
  hasNewCritical: boolean;
}

interface AlertsContextType {
  alerts: Alert[];
  isLoading: boolean;
  error: string | null;
  isOffline: boolean;
  fetchAlerts: () => Promise<void>;
  acknowledgeAlert: (id: string) => Promise<void>;
  completeAlert: (id: string) => Promise<void>;
  criticalAlertsData: CriticalAlertsData;
}

const AlertsContext = createContext<AlertsContextType | undefined>(undefined);

const POLL_INTERVAL = 30000;

// Com o WebSocket conectado o polling desacelera, mas NUNCA para.
//
// Antes era `enabled: !wsConnected`: uma conexão aberta era tratada como
// garantia de que as mensagens chegam. Não é — a conexão pode estar viva e o
// servidor não publicar nada (foi exatamente o que acontecia: nada anunciava
// alerta novo). Numa tela de monitoramento de leito, a falha de um canal não
// pode significar tela congelada sem ninguém perceber: o segundo canal existe
// para que o defeito de um vire atraso, e não ausência.
const POLL_INTERVAL_COM_WS = 120000;

export function AlertsProvider({ children }: { children: ReactNode }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(false);

  const { isConnected: wsConnected, subscribe } = useWebSocketContext();

  const fetchAlerts = useCallback(async () => {
    // Don't set loading to true on background fetches to avoid UI flicker
    if (alerts.length === 0) setIsLoading(true);
    
    try {
      const data = await alertsApi.getAlerts();
      setAlerts(data);
      setError(null);
      setIsOffline(false);
    } catch (err) {
      // Antes este bloco só chamava console.error: `error` ficava null e a
      // tela seguia exibindo a ÚLTIMA lista carregada, sem qualquer indicação
      // de que os dados pararam de atualizar. Num monitor de leito isso é pior
      // do que uma tela de erro — a equipe decide sobre dado velho achando que
      // é atual. (Mesma classe da detecção de silêncio do backend.)
      //
      // A lista anterior é mantida de propósito: apagá-la mostraria "nenhum
      // alerta", que é justamente a leitura errada. Ela fica na tela, mas
      // acompanhada do aviso.
      //
      // `err.status === 0` nunca acontecia: uma falha de rede do fetch lança
      // TypeError, não ApiException, então o ramo inteiro era inalcançável.
      const falhaDeRede = err instanceof TypeError || !navigator.onLine;
      setIsOffline(falhaDeRede);

      if (falhaDeRede) {
        setError('Sem conexão com o servidor. Os alertas exibidos podem estar desatualizados.');
      } else if (err instanceof ApiException) {
        setError(`Falha ao atualizar alertas: ${err.message}`);
      } else {
        setError('Falha ao atualizar alertas. Os dados exibidos podem estar desatualizados.');
      }
      console.error('Error fetching alerts:', err);
    } finally {
      setIsLoading(false);
    }
  }, [alerts.length]);

  // WebSocket handler
  const handleWebSocketMessage = useCallback((message: any) => {
    // `alert_new` = o motor abriu um alerta: alguém precisa virar um paciente.
    // Só `prev.map` NÃO daria conta — map atualiza itens existentes e não
    // consegue inserir. Mesmo que o backend anunciasse (e não anunciava), um
    // alerta novo jamais apareceria na tela. Aqui recarrega-se a lista, que
    // além de inserir traz nome, quarto, leito e horários já calculados pelo
    // servidor — dado que a mensagem não carrega e que a tela não deve inventar.
    if (message.type === 'alert_new') {
      fetchAlerts();
      return;
    }

    if (message.type === 'alert_update') {
      const { alert_id, status } = message;
      if (alert_id && status) {
        setAlerts((prev) =>
          prev.map((alert) =>
            alert.id === alert_id
              ? { ...alert, status: status as Alert['status'] }
              : alert
          )
        );
      }
    }
  }, [fetchAlerts]);

  useEffect(() => {
    return subscribe(handleWebSocketMessage);
  }, [subscribe, handleWebSocketMessage]);

  // Initial fetch
  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Polling — sempre ativo, mais lento quando o WS está conectado.
  const { stop, start } = usePolling({
    interval: wsConnected ? POLL_INTERVAL_COM_WS : POLL_INTERVAL,
    enabled: true,
    onPoll: fetchAlerts,
  });

  // Global Critical Alerts Monitoring
  const criticalAlertsData = useCriticalAlerts(alerts, {
    enabled: true,
    soundEnabled: true,
    notificationsEnabled: true,
  });

  const acknowledgeAlert = async (alertId: string) => {
    stop(); // Pause polling
    try {
      // Optimistic update
      setAlerts((prev) =>
        prev.map((alert) =>
          alert.id === alertId
            ? { ...alert, status: 'acknowledged' as const }
            : alert
        )
      );

      await alertsApi.acknowledge(alertId);
      toast.success('Alerta reconhecido');
      
      // Refresh to ensure sync
      setTimeout(() => fetchAlerts(), 800);
    } catch (err) {
      await fetchAlerts(); // Revert on error
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao reconhecer alerta');
      }
      throw err;
    } finally {
      start(); // Resume polling
    }
  };

  const completeAlert = async (alertId: string) => {
    stop(); // Pause polling
    try {
      await alertsApi.complete(alertId);
      
      // Update status to completed
      setAlerts((prev) =>
        prev.map((alert) =>
          alert.id === alertId
            ? { ...alert, status: 'completed' as const }
            : alert
        )
      );
      
      toast.success('Paciente reposicionado com sucesso');
    } catch (err) {
      await fetchAlerts(); // Revert on error
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao completar alerta');
      }
      throw err;
    } finally {
      start(); // Resume polling
    }
  };

  return (
    <AlertsContext.Provider 
      value={{ 
        alerts, 
        isLoading, 
        error, 
        isOffline, 
        fetchAlerts, 
        acknowledgeAlert, 
        completeAlert,
        criticalAlertsData 
      }}
    >
      {children}
    </AlertsContext.Provider>
  );
}

export function useAlerts() {
  const context = useContext(AlertsContext);
  if (context === undefined) {
    throw new Error('useAlerts must be used within an AlertsProvider');
  }
  return context;
}
