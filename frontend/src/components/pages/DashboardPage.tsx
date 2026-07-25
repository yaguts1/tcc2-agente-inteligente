import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Bell, Calendar } from 'lucide-react';
import { statsApi, DashboardStats, patientsApi, ApiException } from '../../lib/api';
import { AlertFilters } from '../../hooks/useAlertFilters';
import { useAlerts } from '../../contexts/AlertsContext';
import { FilterBar } from '../alerts/FilterBar';
import { Card } from '../ui/card';
import { ErrorBanner } from '../shared/ErrorBanner';
import { PollIndicator } from '../shared/PollIndicator';
import { AlertsTable } from '../alerts/AlertsTable';
import { Skeleton } from '../ui/skeleton';

const POLL_INTERVAL = 30000;

export function DashboardPage() {
  const { 
    alerts, 
    isLoading: alertsLoading, 
    error: alertsError, 
    isOffline: alertsOffline, 
    fetchAlerts, 
    acknowledgeAlert, 
    completeAlert 
  } = useAlerts();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);
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

  const fetchDashboardData = useCallback(async () => {
    setIsLoadingStats(true);
    try {
      const [statsData, patientsData] = await Promise.all([
        statsApi.getStats(),
        patientsApi.getPatients(),
      ]);
      
      setStats(statsData);
      setPatients(patientsData.map((p) => ({ id: p.id, name: p.name })));
      setStatsError(null);
    } catch (err) {
      if (err instanceof ApiException) {
        setStatsError(err.message);
      } else {
        setStatsError('Erro ao carregar dados do dashboard');
      }
    } finally {
      setIsLoadingStats(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  // Refresh stats when alerts change (e.g. via WebSocket in context)
  useEffect(() => {
    statsApi.getStats().then(setStats).catch(console.error);
  }, [alerts]);

  const handleManualRefresh = () => {
    fetchAlerts();
    fetchDashboardData();
  };

  const handleAcknowledge = async (alertId: string) => {
    await acknowledgeAlert(alertId);
    // Refresh stats after action
    statsApi.getStats().then(setStats).catch(console.error);
  };

  const handleComplete = async (alertId: string) => {
    await completeAlert(alertId);
    // Refresh stats after action
    statsApi.getStats().then(setStats).catch(console.error);
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

  const isLoading = alertsLoading || isLoadingStats;
  const error = alertsError || statsError;

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
          isPolling={true} // Context handles polling
          interval={POLL_INTERVAL}
          onManualRefresh={handleManualRefresh}
        />
      </div>

      {/* Error Banner */}
      {error && (
        <ErrorBanner
          type={alertsOffline ? 'offline' : 'error'}
          title={alertsOffline ? 'Conexão perdida' : 'Erro'}
          message={error}
          onRetry={handleManualRefresh}
          onDismiss={() => setStatsError(null)}
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
