import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Bell, Calendar } from 'lucide-react';
import { alertsApi, Alert, ApiException, statsApi, DashboardStats } from '../../lib/api';
import { usePolling } from '../../hooks/usePolling';
import { useWebSocket } from '../../hooks/useWebSocket';
import { useAlertFilters, AlertFilters } from '../../hooks/useAlertFilters';
import { useCriticalAlerts } from '../../hooks/useCriticalAlerts';
import { ExportPanel } from '../ExportPanel';
import { FilterBar } from '../alerts/FilterBar';
import { Card } from '../ui/card';
import { ErrorBanner } from '../shared/ErrorBanner';
import { PollIndicator } from '../shared/PollIndicator';
import { AlertsTable } from '../alerts/AlertsTable';
import { Skeleton } from '../ui/skeleton';
import { toast } from 'sonner';

const POLL_INTERVAL = 30000; // 30 seconds - fallback to polling if WebSocket unavailable

export function DashboardPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(false);
  const [patients, setPatients] = useState<Array<{ id: string; name: string }>>([]);
  const [filters, setFilters] = useState<AlertFilters>({});
  const [activeFilterCount, setActiveFilterCount] = useState(0);

  const updateFilter = useCallback((key: keyof AlertFilters, value: any) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  const clearAllFilters = useCallback(() => {
    setFilters({});
  }, []);

  useEffect(() => {
    const count = Object.values(filters).filter((v) => v !== undefined && v !== '').length;
    setActiveFilterCount(count);
  }, [filters]);

  // Filter alerts based on current filters
  const filteredAlerts = alerts.filter((alert) => {
    // Convert riskLevel to severity for filtering
    const severity = alert.riskLevel === 'high' ? 'HIGH' : alert.riskLevel === 'medium' ? 'MEDIUM' : 'LOW';
    if (filters.severity && severity !== filters.severity) {
      return false;
    }
    if (filters.status && alert.status !== filters.status) {
      return false;
    }
    return true;
  });

  // Critical alerts hook
  const {
    criticalAlerts,
    totalCritical,
    highRisk,
    acknowledgedMedium,
    hasNewCritical,
  } = useCriticalAlerts(alerts, {
    enabled: true,
    soundEnabled: true,
    notificationsEnabled: true,
  });

  const fetchAlerts = useCallback(async () => {
    setIsLoading(true);
    try {
      const alertsData = await alertsApi.getAlerts();
      const statsData = await statsApi.getStats();
      setAlerts(alertsData);
      setStats(statsData);
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

  // WebSocket handler for real-time alert updates
  const handleWebSocketMessage = useCallback((message: any) => {
    if (message.type === 'alert_update') {
      // Update alert status based on WebSocket message
      const { alert_id, status } = message;
      if (alert_id && status) {
        setAlerts((prev) =>
          prev.map((alert) =>
            alert.id === alert_id
              ? { ...alert, status: status as Alert['status'] }
              : alert
          )
        );
        
        // Also refresh stats to keep them in sync
        statsApi.getStats().then(setStats).catch(console.error);
      }
    }
  }, []);

  // WebSocket connection for real-time updates
  const { isConnected: wsConnected } = useWebSocket({
    enabled: true,
    onMessage: handleWebSocketMessage,
  });

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Polling as fallback (disabled if WebSocket is working, but kept for resilience)
  const { isPolling, stop, start } = usePolling({
    interval: POLL_INTERVAL,
    enabled: !wsConnected, // Only enable polling if WebSocket not connected
    onPoll: fetchAlerts,
  });

  const handleAcknowledge = async (alertId: string) => {
    // pause polling while we perform the action to avoid races
    stop();
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

      // refresh shortly to reconcile any server-side changes
      setTimeout(() => fetchAlerts(), 800);
    } catch (err) {
      // Revert on error
      await fetchAlerts();
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao reconhecer alerta');
      }
    } finally {
      start();
    }
  };

  const handleComplete = async (alertId: string) => {
    // pause polling while we perform the action
    stop();
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
      setTimeout(() => fetchAlerts(), 1000);
    } catch (err) {
      // Revert on error
      await fetchAlerts();
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao completar alerta');
      }
    } finally {
      start();
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

      {/* Export Panel */}
      <ExportPanel
        onSuccess={(msg) => toast.success(msg)}
        onError={(msg) => toast.error(msg)}
      />

      {/* Filter Bar */}
      <FilterBar
        filters={filters}
        onFilterChange={updateFilter}
        onClearFilters={clearAllFilters}
        activeFilterCount={activeFilterCount}
        patients={patients}
      />

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
                <p className="text-foreground">{stats?.activeAlerts ?? 0}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-danger/10 p-2 rounded-lg">
                <AlertTriangle className="w-5 h-5 text-danger" />
              </div>
              <div>
                <p className="text-muted-foreground">Reconhecidos</p>
                <p className="text-danger">{stats?.acknowledgedAlerts ?? 0}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-warning/10 p-2 rounded-lg">
                <Calendar className="w-5 h-5 text-warning" />
              </div>
              <div>
                <p className="text-muted-foreground">Completados Hoje</p>
                <p className="text-foreground">{stats?.completedToday ?? 0}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-success/10 p-2 rounded-lg">
                <Calendar className="w-5 h-5 text-success" />
              </div>
              <div>
                <p className="text-muted-foreground">Taxa de Conclusão</p>
                <p className="text-foreground">{stats?.completionRate ?? 0}%</p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Alerts Table */}
      <Card>
        <AlertsTable
          alerts={filteredAlerts}
          onAcknowledge={handleAcknowledge}
          onComplete={handleComplete}
          isLoading={isLoading}
        />
      </Card>
    </div>
  );
}
