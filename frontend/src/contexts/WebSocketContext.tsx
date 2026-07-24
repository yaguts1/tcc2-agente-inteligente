import React, { createContext, useContext, ReactNode, useRef, useCallback } from 'react';
import { useWebSocket, AlertUpdate } from '../hooks/useWebSocket';

type Listener = (msg: AlertUpdate) => void;

interface WebSocketContextType {
  isConnected: boolean;
  subscribe: (listener: Listener) => () => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export function WebSocketProvider({ children, isAuthenticated }: { children: ReactNode; isAuthenticated: boolean }) {
  const listenersRef = useRef<Set<Listener>>(new Set());

  const { isConnected } = useWebSocket({
    enabled: true,
    isAuthenticated,
    onMessage: (msg) => {
      listenersRef.current.forEach((listener) => {
        try {
          listener(msg);
        } catch (error) {
          console.error('Error in WebSocket listener:', error);
        }
      });
    },
  });

  const subscribe = useCallback((listener: Listener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  return (
    <WebSocketContext.Provider value={{ isConnected, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocketContext() {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
}
