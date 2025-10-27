import { useEffect, useRef, useCallback, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from './useAuth';

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
}

export function useWebSocket({
  enabled = true,
  onMessage,
  reconnectInterval = 3000,
  maxReconnectAttempts = 5,
}: UseWebSocketOptions = {}) {
  const { isAuthenticated } = useAuth();
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
      fetch('/api/stats', { signal: AbortSignal.timeout(2000) })
        .then(() => {
          const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const url = `${protocol}//${window.location.host}/api/ws/alerts`;
          
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
              console.log(`Attempting to reconnect (${reconnectAttemptsRef.current}/${maxReconnectAttempts})...`);
              
              if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
              }
              
              reconnectTimeoutRef.current = setTimeout(() => {
                connect();
              }, reconnectInterval);
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
