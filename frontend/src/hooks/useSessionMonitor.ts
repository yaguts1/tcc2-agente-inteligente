/**
 * Hook for monitoring session expiration
 * Warns user before session expires and handles automatic logout
 */

import { useEffect, useState } from 'react';
import { getSessionTimeRemaining, isSessionValid } from '../lib/storage';

interface SessionWarningConfig {
  warningThreshold?: number; // ms before expiry to show warning (default: 5 minutes)
  checkInterval?: number; // ms between checks (default: 30 seconds)
  onWarning?: (timeRemaining: number) => void;
  onExpire?: () => void;
  enabled?: boolean;
}

export function useSessionMonitor(config: SessionWarningConfig = {}) {
  const {
    warningThreshold = 5 * 60 * 1000, // 5 minutes
    checkInterval = 30 * 1000, // 30 seconds
    onWarning,
    onExpire,
    enabled = true,
  } = config;

  const [isExpired, setIsExpired] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(getSessionTimeRemaining());
  const [warningShown, setWarningShown] = useState(false);

  useEffect(() => {
    if (!enabled) return;

    const checkSession = () => {
      const remaining = getSessionTimeRemaining();
      setTimeRemaining(remaining);

      if (remaining <= 0) {
        // Session has expired
        setIsExpired(true);
        onExpire?.();
        console.warn('[useSessionMonitor] Session expired');
      } else if (remaining <= warningThreshold && !warningShown) {
        // Show warning
        setWarningShown(true);
        onWarning?.(remaining);
        console.warn('[useSessionMonitor] Session expiring soon', { remaining, threshold: warningThreshold });
      }
    };

    // Check immediately
    checkSession();

    // Set up interval
    const interval = setInterval(checkSession, checkInterval);

    return () => clearInterval(interval);
  }, [enabled, warningThreshold, checkInterval, onWarning, onExpire, warningShown]);

  const formatTimeRemaining = (): string => {
    const ms = timeRemaining;
    const minutes = Math.floor(ms / (60 * 1000));
    const seconds = Math.floor((ms % (60 * 1000)) / 1000);

    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
  };

  return {
    isExpired,
    timeRemaining,
    isValid: isSessionValid(),
    formatTimeRemaining,
  };
}
