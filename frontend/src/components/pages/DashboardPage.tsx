import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Bell, Calendar } from 'lucide-react';
import { statsApi, DashboardStats, patientsApi, ApiException, Alert, monitoramentoApi, StatusMonitoramento } from '../../lib/api';
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
    totalTruncadoEm,
    fetchAlerts, 
    acknowledgeAlert, 
    completeAlert,
    acknowledgeAlertsEmLote,
    completeAlertsEmLote
  } = useAlerts();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  // QUAIS pacientes estão sem dados. `/api/stats` só traz a contagem, e o aviso
  // que dizia "3 pacientes sem monitoramento" não dava como saber quais leitos
  // conferir — a informação existia em /api/monitoramento e ninguém pedia.
  const [semMonitoramento, setSemMonitoramento] = useState<StatusMonitoramento[]>([]);
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
      const [statsData, patientsData, monitoramento] = await Promise.all([
        statsApi.getStats(),
        patientsApi.getPatients(),
        // Falha aqui é benigna: o aviso agregado (vindo de /stats) continua
        // aparecendo, só sem a lista de quem. Deixar o dashboard inteiro cair
        // por causa do detalhe seria pior do que perder o detalhe.
        monitoramentoApi.getStatus().catch(() => null),
      ]);

      setStats(statsData);
      setPatients(patientsData.map((p) => ({ id: p.id, name: p.name })));
      setSemMonitoramento(monitoramento?.pacientes_sem_monitoramento ?? []);
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

  // As ações mudam o array `alerts`, e o efeito acima já refaz o fetch de
  // stats por causa disso — não é preciso chamar getStats() aqui de novo.
  const handleAcknowledge = async (alertId: string) => {
    await acknowledgeAlert(alertId);
  };

  const handleComplete = async (alertId: string) => {
    await completeAlert(alertId);
  };

  // Métricas exibidas nos cards.
  //
  // Antes, `stats` (a resposta de /api/stats) era escrito quatro vezes e lido
  // ZERO: os cards mostravam este recálculo client-side, que usa uma fórmula
  // DIFERENTE da do backend — `completados / total` da visão atual, contra
  // `fechados / (abertos + reconhecidos + fechados)` nas últimas 24h. Ou seja,
  // o rótulo "Taxa de Conclusão" exibia outra métrica que não a calculada (e
  // corrigida) no servidor, e a requisição era feita à toa.
  //
  // Agora: sem filtro ativo, mostra o número do backend, que é a fonte
  // autoritativa e usa uma janela de 24h consistente. Com filtro, recalcula
  // sobre a visão filtrada — mas com a MESMA fórmula do backend, para os
  // rótulos continuarem significando a mesma coisa.
  const temFiltroAtivo = activeFilterCount > 0;

  const contarPorStatus = (status: Alert['status']) =>
    filteredAlerts.filter((a) => a.status === status).length;

  const displayStats = (() => {
    if (!temFiltroAtivo) {
      return {
        activeAlerts: stats?.activeAlerts ?? 0,
        acknowledgedAlerts: stats?.acknowledgedAlerts ?? 0,
        completedToday: stats?.completedToday ?? 0,
        completionRate: stats?.completionRate ?? 0,
      };
    }
    const pendentes = contarPorStatus('pending');
    const reconhecidos = contarPorStatus('acknowledged');
    const concluidos = contarPorStatus('completed');
    const total = pendentes + reconhecidos + concluidos;
    return {
      activeAlerts: pendentes,
      acknowledgedAlerts: reconhecidos,
      completedToday: concluidos,
      completionRate: total > 0 ? Math.round((concluidos / total) * 100) : 0,
    };
  })();

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

      {/*
        Aviso de monitoramento interrompido.
        Fica ACIMA de tudo e não pode ser dispensado: o sistema é orientado a
        evento, então um sensor morto não gera erro nenhum — apenas para de
        produzir alertas, e a tela ficava dizendo "todos os pacientes em dia".
        Sem este aviso, silêncio é indistinguível de normalidade, que é o pior
        modo de falha num monitoramento de segurança do paciente.
      */}
      {(stats?.unmonitoredPatients ?? 0) > 0 && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-danger bg-danger-light p-4"
        >
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
          <div>
            <p className="font-bold text-foreground">
              {stats!.unmonitoredPatients === 1
                ? '1 paciente sem monitoramento'
                : `${stats!.unmonitoredPatients} pacientes sem monitoramento`}
            </p>
            <p className="text-sm text-muted-foreground">
              Sem leituras há mais de {stats!.monitoringLimitMin} minutos. A ausência de
              alertas <strong>não</strong> significa que está tudo bem — verifique o sensor,
              a rede do leito e a ingestão.
            </p>
            {/*
              Quem, e não só quantos. O aviso mandava "verificar o sensor" sem
              dizer de qual leito: a lista existia em /api/monitoramento e
              nenhuma tela pedia. `nunca_recebeu_dados` aparece separado porque
              a ação corretiva é outra — não é sensor que parou, é instalação
              ou vínculo device↔leito que nunca funcionou.
            */}
            {semMonitoramento.length > 0 && (
              <ul className="mt-2 space-y-1 text-sm text-foreground">
                {semMonitoramento.map((p) => (
                  <li key={p.paciente_id}>
                    <span className="font-medium">{p.nome || p.paciente_id}</span>
                    {p.cama_id && <span className="text-muted-foreground"> — leito {p.cama_id}</span>}
                    <span className="text-muted-foreground">
                      {p.nunca_recebeu_dados
                        ? ' — nunca recebeu leitura (verifique a instalação e o vínculo do dispositivo)'
                        : p.minutos_sem_dados != null
                          ? ` — sem dados há ${p.minutos_sem_dados} min`
                          : ' — sem leitura recente'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/*
        Lista de alertas cortada pelo teto da requisição.
        O filtro da tela roda em MEMÓRIA sobre o que chegou, então o que foi
        cortado não existe para a busca — e um paciente atrasado ficaria fora
        sem nenhum sinal. Mesmo princípio do relatório truncado: a omissão
        pode até ser aceitável, invisível não.
      */}
      {totalTruncadoEm !== null && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-warning bg-warning-light p-4"
        >
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
          <p className="text-sm text-foreground">
            Exibindo {alerts.length} de <strong>{totalTruncadoEm}</strong> alertas da janela.
            Os filtros abaixo se aplicam apenas aos exibidos — restrinja o período para ver
            o restante.
          </p>
        </div>
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
                <p className="text-2xl font-bold text-foreground">{displayStats.activeAlerts}</p>
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
                <p className="text-2xl font-bold text-warning">{displayStats.acknowledgedAlerts}</p>
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
                <p className="text-2xl font-bold text-success">{displayStats.completedToday}</p>
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
                <p className="text-2xl font-bold text-foreground">{displayStats.completionRate}%</p>
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
          onBulkAcknowledge={acknowledgeAlertsEmLote}
          onBulkComplete={completeAlertsEmLote}
          isLoading={isLoading}
        />
      </Card>
    </div>
  );
}
