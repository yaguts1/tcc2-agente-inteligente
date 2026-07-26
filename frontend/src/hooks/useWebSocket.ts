import { useEffect, useRef, useCallback, useState } from 'react';
import { toast } from 'sonner';

export interface AlertUpdate {
  type: 'alert_update' | 'alert_new' | string;
  alert_id?: string;
  status?: 'pending' | 'acknowledged' | 'completed';
  timestamp?: string;
  [key: string]: unknown;
}

interface UseWebSocketOptions {
  enabled?: boolean;
  onMessage?: (message: AlertUpdate) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  isAuthenticated?: boolean;
}

export function useWebSocket({
  enabled = true,
  onMessage,
  reconnectInterval = 5000, // Aumentado de 3s para 5s
  maxReconnectAttempts = 5,
  isAuthenticated = false,
}: UseWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const connect = useCallback(() => {
    if (!enabled || !isAuthenticated) {
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    try {
      // Check if backend is reachable first (prevent connection spam)
      fetch(`${import.meta.env.BASE_URL}api/stats`, { signal: AbortSignal.timeout(2000) })
        .then(() => {
          const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const baseUrl = import.meta.env.BASE_URL;
          // SEM query string, de propósito.
          //
          // `/api/ws/alerts` aceita ?severity=, ?patient_id= e ?alert_types=,
          // e o filtro é POR CONEXÃO. Esta conexão é ÚNICA e compartilhada
          // (WebSocketContext): o dashboard precisa de todos os alertas e a
          // tela de Histórico recarrega a timeline a cada mensagem. Qualquer
          // filtro aqui silenciaria os outros consumidores.
          //
          // Se um dia uma tela precisar de um recorte (ex.: painel de um leito
          // só), abra uma SEGUNDA conexão para ela — não filtre esta.
          const url = `${protocol}//${window.location.host}${baseUrl}api/ws/alerts`;

          const ws = new WebSocket(url);

          ws.onopen = () => {
            console.log('WebSocket connected');
            setIsConnected(true);
            setLastError(null);
            reconnectAttemptsRef.current = 0;
            toast.success('Conectado a alertas em tempo real');
            
            // Send heartbeat every 30 seconds to keep connection alive
            const heartbeatInterval = setInterval(() => {
              if (ws.readyState === WebSocket.OPEN) {
                try {
                  ws.send(JSON.stringify({ type: 'ping' }));
                } catch (err) {
                  console.error('Heartbeat send error:', err);
                }
              }
            }, 30000);

            // Store interval ID for cleanup
            (ws as any)._heartbeatInterval = heartbeatInterval;
          };

          ws.onmessage = (event) => {
            try {
              const message: AlertUpdate = JSON.parse(event.data);
              console.log('WebSocket message received:', message);
              onMessage?.(message);
            } catch (err) {
              console.error('Failed to parse WebSocket message:', err, event.data);
            }
          };

          ws.onerror = (event) => {
            console.error('WebSocket error:', event);
            const errorMsg = 'Erro na conexão com alertas em tempo real';
            setLastError(errorMsg);
            toast.error(errorMsg);
          };

          ws.onclose = () => {
            console.log('WebSocket disconnected');
            setIsConnected(false);
            
            // Clear heartbeat interval
            if ((ws as any)._heartbeatInterval) {
              clearInterval((ws as any)._heartbeatInterval);
            }

            // Attempt to reconnect if enabled and authenticated
            if (enabled && isAuthenticated && reconnectAttemptsRef.current < maxReconnectAttempts) {
              reconnectAttemptsRef.current += 1;
              
              // Exponential backoff: 1x, 2x, 4x, 8x, 16x
              const exponentialDelay = reconnectInterval * Math.pow(2, reconnectAttemptsRef.current - 1);
              const maxDelay = 30000; // Max 30 segundos
              const delayMs = Math.min(exponentialDelay, maxDelay);
              
              console.log(`Attempting to reconnect (${reconnectAttemptsRef.current}/${maxReconnectAttempts})... waiting ${delayMs}ms`);
              
              if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
              }
              
              reconnectTimeoutRef.current = setTimeout(() => {
                connect();
              }, delayMs);
            } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
              setLastError('Máximo de tentativas de reconexão atingido');
              toast.error('Conexão com alertas em tempo real perdida. Por favor, recarregue a página.');
            }
          };

          wsRef.current = ws;
        })
        .catch(() => {
          // Backend not reachable, fall back to polling (already handled by DashboardPage)
          console.warn('Backend not reachable, using polling as fallback');
          setLastError(null); // Don't show error, polling will handle it
        });
    } catch (err) {
      const errorMsg = `Falha ao conectar ao WebSocket: ${err}`;
      console.error(errorMsg);
      setLastError(errorMsg);
      toast.error(errorMsg);
    }
  }, [enabled, isAuthenticated, onMessage, reconnectInterval, maxReconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      if ((wsRef.current as any)._heartbeatInterval) {
        clearInterval((wsRef.current as any)._heartbeatInterval);
      }
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  // Connect on mount if enabled and authenticated
  useEffect(() => {
    if (enabled && isAuthenticated) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      if (!enabled || !isAuthenticated) {
        disconnect();
      }
    };
  }, [enabled, isAuthenticated, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    lastError,
    reconnectAttempts: reconnectAttemptsRef.current,
  };
}
