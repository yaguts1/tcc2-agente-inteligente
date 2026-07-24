import { useEffect, useRef, useState } from 'react';

interface UsePollingOptions {
  interval: number;
  enabled?: boolean;
  onPoll: () => void | Promise<void>;
}

export function usePolling({ interval, enabled = true, onPoll }: UsePollingOptions) {
  const [isPolling, setIsPolling] = useState(enabled);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // `enabled` é uma prop que muda em runtime (ex: `enabled={!wsConnected}` —
  // pausar o polling quando o WebSocket conecta). Sem este efeito, `isPolling`
  // só era lido de `enabled` na montagem e o polling NUNCA parava ao mudar a
  // prop.
  useEffect(() => {
    setIsPolling(enabled);
  }, [enabled]);

  useEffect(() => {
    if (!isPolling) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = setInterval(() => {
      onPoll();
    }, interval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isPolling, interval, onPoll]);

  const toggle = () => setIsPolling((prev) => !prev);
  const start = () => setIsPolling(true);
  const stop = () => setIsPolling(false);

  return {
    isPolling,
    toggle,
    start,
    stop,
  };
}
