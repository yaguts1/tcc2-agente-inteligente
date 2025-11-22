import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Bell, Calendar } from 'lucide-react';
import { alertsApi, Alert, ApiException, statsApi, DashboardStats, patientsApi } from '../../lib/api';
import { usePolling } from '../../hooks/usePolling';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import { useAlertFilters, AlertFilters } from '../../hooks/useAlertFilters';
import { useCriticalAlerts } from '../../hooks/useCriticalAlerts';
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
    // Filter by severity (riskLevel)
    if (filters.severity) {
      const alertSeverity = alert.riskLevel === 'high' ? 'HIGH' : 
                           alert.riskLevel === 'medium' ? 'MEDIUM' : 'LOW';
      if (alertSeverity !== filters.severity) {
        return false;
      }
    }
    
    // Filter by status (pending, acknowledged, completed)
    if (filters.status && alert.status !== filters.status) {
      return false;
    }
    
    // Filter by patient ID
    if (filters.patientId) {
      const alertPatientId = alert.id.split('__')[0];
      if (alertPatientId !== filters.patientId) {
        return false;
      }
    }
    
    // Filter by search text
    if (filters.searchText) {
      const searchLower = filters.searchText.toLowerCase();
      const matchesPatient = alert.patientName.toLowerCase().includes(searchLower);
      const matchesRoom = alert.room.toLowerCase().includes(searchLower);
      const matchesBed = alert.bed.toLowerCase().includes(searchLower);
      if (!matchesPatient && !matchesRoom && !matchesBed) {
        return false;
      }
    }
    
    // Filter by date range
    if (filters.dateFrom) {
      const alertDate = new Date(alert.nextRepositioning);
      if (alertDate < filters.dateFrom) {
        return false;
      }
    }
    
    if (filters.dateTo) {
      const alertDate = new Date(alert.nextRepositioning);
      if (alertDate > filters.dateTo) {
        return false;
      }
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
      const [alertsData, statsData, patientsData] = await Promise.all([
        alertsApi.getAlerts(),
        statsApi.getStats(),
        patientsApi.getPatients(),
      ]);
      
      // Store all alerts (including completed) to allow correct stats calculation
      setAlerts(alertsData);
      setStats(statsData);
      setPatients(patientsData.map((p) => ({ id: p.id, name: p.name })));
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
        // Update status for all alerts (including completed)
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
  const { isConnected: wsConnected, subscribe } = useWebSocketContext();

  useEffect(() => {
    return subscribe(handleWebSocketMessage);
  }, [subscribe, handleWebSocketMessage]);

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
      await alertsApi.complete(alertId);
      
      // Update status to completed (don't remove, so stats stay correct)
      setAlerts((prev) =>
        prev.map((alert) =>
          alert.id === alertId
            ? { ...alert, status: 'completed' as const }
            : alert
        )
      );
      
      toast.success('Paciente reposicionado com sucesso');

      // Refresh stats to update metrics
      statsApi.getStats().then(setStats).catch(console.error);
    } catch (err) {
      // Refresh on error to get accurate state
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

  // Calculate metrics from filtered alerts
  const filteredStats = {
    activeAlerts: filteredAlerts.filter(a => a.status === 'pending').length,
    acknowledgedAlerts: filteredAlerts.filter(a => a.status === 'acknowledged').length,
    completedToday: filteredAlerts.filter(a => a.status === 'completed').length,
    totalAlerts: filteredAlerts.length,
    completionRate: filteredAlerts.length > 0 
      ? Math.round((filteredAlerts.filter(a => a.status === 'completed').length / filteredAlerts.length) * 100)
      : 0
  };

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
                <p className="text-sm text-muted-foreground">Alertas Ativos</p>
                <p className="text-2xl font-bold text-foreground">{filteredStats.activeAlerts}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-warning/10 p-2 rounded-lg">
                <AlertTriangle className="w-5 h-5 text-warning" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Reconhecidos</p>
                <p className="text-2xl font-bold text-warning">{filteredStats.acknowledgedAlerts}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-success/10 p-2 rounded-lg">
                <Calendar className="w-5 h-5 text-success" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Completados Hoje</p>
                <p className="text-2xl font-bold text-success">{filteredStats.completedToday}</p>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-3">
              <div className="bg-blue-500/10 p-2 rounded-lg">
                <Calendar className="w-5 h-5 text-blue-500" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Taxa de Conclusão</p>
                <p className="text-2xl font-bold text-foreground">{filteredStats.completionRate}%</p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Alerts Table */}
      <Card>
        <AlertsTable
          alerts={filteredAlerts.filter(a => {
            // If user explicitly filtered by status, show what they asked for
            if (filters.status) return true;
            // Otherwise, hide completed by default to keep table clean
            return a.status !== 'completed';
          })}
          onAcknowledge={handleAcknowledge}
          onComplete={handleComplete}
          isLoading={isLoading}
        />
      </Card>
    </div>
  );
}
