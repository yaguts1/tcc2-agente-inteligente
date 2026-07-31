/**
 * Session Expiration Alert Component
 * Displays warning and options when session is about to expire
 */

import { useState } from 'react';
import { AlertCircle, LogOut } from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { useAuth } from '../../hooks/useAuth';
import { useSessionMonitor } from '../../hooks/useSessionMonitor';

interface SessionExpirationAlertProps {
  /** Show warning 5 minutes before expiry (default: true) */
  showWarning?: boolean;
  /** Callback when user clicks "Extend Session" */
  onExtendSession?: () => void;
}

export function SessionExpirationAlert({ showWarning = true, onExtendSession }: SessionExpirationAlertProps) {
  const { logout } = useAuth();
  const [showAlert, setShowAlert] = useState(false);
  const [sessionExpiring, setSessionExpiring] = useState(false);

  const { isExpired, formatTimeRemaining } = useSessionMonitor({
    enabled: showWarning,
    onWarning: (timeRemaining) => {
      setShowAlert(true);
      setSessionExpiring(timeRemaining > 0);
    },
    onExpire: () => {
      setSessionExpiring(false);
      setShowAlert(true);
    },
  });

  const handleExtend = () => {
    onExtendSession?.();
    setShowAlert(false);
    // Reload page to refresh session
    window.location.reload();
  };

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  if (!showAlert) return null;

  if (isExpired) {
    return (
      <Card className="fixed bottom-4 right-4 w-96 border-destructive bg-destructive/10">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-destructive">Sessão Expirada</h3>
              <p className="text-sm text-muted-foreground mt-1">Sua sessão expirou. Por favor, faça login novamente.</p>
              <div className="flex gap-2 mt-4">
                <Button variant="destructive" size="sm" onClick={handleLogout}>
                  <LogOut className="w-4 h-4 mr-2" />
                  Voltar ao Login
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (sessionExpiring) {
    return (
      <Card className="fixed bottom-4 right-4 w-96 border-yellow-600 bg-yellow-50 dark:bg-yellow-950">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <AlertCircle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-yellow-900 dark:text-yellow-100 dark:text-yellow-900">Sessão Expirando</h3>
              <p className="text-sm text-yellow-800 dark:text-yellow-200 mt-1">
                Sua sessão expira em {formatTimeRemaining()}
              </p>
              <div className="flex gap-2 mt-4">
                <Button
                  size="sm"
                  onClick={handleExtend}
                  className="bg-yellow-600 hover:bg-yellow-700 text-white"
                >
                  Estender Sessão
                </Button>
                <Button variant="outline" size="sm" onClick={handleLogout}>
                  Logout
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return null;
}
