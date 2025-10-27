import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Bell, Calendar } from 'lucide-react';
import { alertsApi, Alert, ApiException } from '../../lib/api';
import { usePolling } from '../../hooks/usePolling';
import { Card } from '../ui/card';
import { ErrorBanner } from '../shared/ErrorBanner';
import { PollIndicator } from '../shared/PollIndicator';
import { AlertsTable } from '../alerts/AlertsTable';
import { Skeleton } from '../ui/skeleton';
import { toast } from 'sonner';

const POLL_INTERVAL = 30000; // 30 seconds

export function DashboardPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(false);

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await alertsApi.getAlerts();
      setAlerts(data);
      setError(null);
      setIsOffline(false);
    } catch (err) {
      if (err instanceof ApiException) {
        if (err.status === 0 || !navigator.onLine) {
          setIsOffline(true);
          setError('Sem conexão com o servidor');
        } else {
          setError(err.message);
        }
      } else {
        setError('Erro ao carregar alertas');
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const { isPolling, stop, start } = usePolling({
    interval: POLL_INTERVAL,
    enabled: true,
    onPoll: fetchAlerts,
  });

  const handleAcknowledge = async (alertId: string) => {
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
    } catch (err) {
      // Revert on error
      await fetchAlerts();
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao reconhecer alerta');
      }
    }
  };

  const handleComplete = async (alertId: string) => {
    try {
      // Optimistic update
      setAlerts((prev) =>
        prev.map((alert) =>
          alert.id === alertId
            ? {
                ...alert,
                status: 'completed' as const,
                lastRepositioning: new Date().toISOString(),
              }
            : alert
        )
      );

      await alertsApi.complete(alertId);
      toast.success('Paciente reposicionado com sucesso');
      
      // Refresh after a short delay to get updated data
      setTimeout(fetchAlerts, 1000);
    } catch (err) {
      // Revert on error
      await fetchAlerts();
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao completar alerta');
      }
    }
  };

  const activeAlerts = alerts.filter((a) => a.status !== 'completed');
  const overdueAlerts = activeAlerts.filter(
    (a) => new Date(a.nextRepositioning) < new Date()
  );
  const acknowledgedAlerts = activeAlerts.filter(
    (a) => a.status === 'acknowledged'
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-foreground">Dashboard</h1>
          <p className="text-muted-foreground">
            Monitor de alertas de reposicionamento
          </p>
        </div>
        <PollIndicator
          isPolling={isPolling}
          interval={POLL_INTERVAL}
          onManualRefresh={fetchAlerts}
        />
      </div>

      {/* Error Banner */}
      {error && (
        <ErrorBanner
          type={isOffline ? 'offline' : 'error'}
          title={isOffline ? 'Conexão perdida' : 'Erro'}
          message={error}
          onRetry={fetchAlerts}
          onDismiss={() => setError(null)}
        />
      )}

      {/* Stats Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Card key={i} className="p-6">
              <Skeleton className="h-4 w-24 mb-2" />
              <Skeleton className="h-8 w-16" />
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-primary/10 p-2 rounded-lg">
                <Bell className="w-5 h-5 text-primary" />
              </div>
              <div>
                <p className="text-muted-foreground">Alertas Ativos</p>
                <p className="text-foreground">{activeAlerts.length}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-danger/10 p-2 rounded-lg">
                <AlertTriangle className="w-5 h-5 text-danger" />
              </div>
              <div>
                <p className="text-muted-foreground">Atrasados</p>
                <p className="text-danger">{overdueAlerts.length}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-warning/10 p-2 rounded-lg">
                <Calendar className="w-5 h-5 text-warning" />
              </div>
              <div>
                <p className="text-muted-foreground">Reconhecidos</p>
                <p className="text-foreground">{acknowledgedAlerts.length}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-success/10 p-2 rounded-lg">
                <Calendar className="w-5 h-5 text-success" />
              </div>
              <div>
                <p className="text-muted-foreground">Taxa de Sucesso</p>
                <p className="text-foreground">
                  {alerts.length > 0
                    ? Math.round(
                        (alerts.filter((a) => a.status === 'completed').length /
                          alerts.length) *
                          100
                      )
                    : 0}
                  %
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Alerts Table */}
      <Card>
        <AlertsTable
          alerts={activeAlerts}
          onAcknowledge={handleAcknowledge}
          onComplete={handleComplete}
          isLoading={isLoading}
        />
      </Card>
    </div>
  );
}
