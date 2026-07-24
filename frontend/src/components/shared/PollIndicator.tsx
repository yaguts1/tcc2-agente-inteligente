import { RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { cn } from '../ui/utils';

interface PollIndicatorProps {
  isPolling: boolean;
  interval: number;
  onManualRefresh?: () => void;
}

export function PollIndicator({
  isPolling,
  interval,
  onManualRefresh,
}: PollIndicatorProps) {
  const [secondsUntilNext, setSecondsUntilNext] = useState(interval / 1000);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    if (!isPolling) return;

    setSecondsUntilNext(interval / 1000);
    
    const timer = setInterval(() => {
      setSecondsUntilNext((prev) => {
        if (prev <= 1) {
          return interval / 1000;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isPolling, interval]);

  const handleManualRefresh = () => {
    if (onManualRefresh && !isRefreshing) {
      setIsRefreshing(true);
      onManualRefresh();
      setTimeout(() => setIsRefreshing(false), 1000);
    }
  };

  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <button
        onClick={handleManualRefresh}
        disabled={isRefreshing || !onManualRefresh}
        className={cn(
          'p-1 rounded hover:bg-muted transition-colors disabled:opacity-50',
          isRefreshing && 'cursor-not-allowed'
        )}
        aria-label="Atualizar agora"
      >
        <RefreshCw
          className={cn('w-4 h-4', isRefreshing && 'animate-spin')}
        />
      </button>
      {isPolling && (
        <span>
          Atualiza em {secondsUntilNext}s
        </span>
      )}
    </div>
  );
}
