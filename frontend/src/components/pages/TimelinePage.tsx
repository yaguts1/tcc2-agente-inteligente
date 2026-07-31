import { useCallback, useEffect, useState } from 'react';
import { timelineApi, TimelineEvent, ApiException, patientsApi, Patient, TimelineFilters } from '../../lib/api';
import { useWebSocketContext } from '../../contexts/WebSocketContext';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { ExportPanel } from '../ExportPanel';
import { 
  CheckCircle2, 
  Eye, 
  AlertCircle, 
  Clock, 
  Filter,
  X,
  RefreshCw,
  Calendar as CalendarIcon
} from 'lucide-react';
import { toast } from 'sonner';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

const PAGE_SIZE = 100;

/**
 * Converte o "YYYY-MM-DD" de um <input type="date"> no instante inicial ou
 * final daquele dia NO FUSO DO USUARIO.
 *
 * O caminho anterior era `new Date(valor)` seguido de `setHours(...)`, e o
 * primeiro passo ja estava errado: a forma so-data do ISO 8601 e interpretada
 * como meia-noite UTC, nao local. No Brasil (UTC-3), `new Date('2026-07-26')`
 * e 25/07 as 21:00 locais, e o `setHours(0,0,0,0)` zerava o dia 25. Filtrar
 * "26/07 a 26/07" pedia ao backend a janela do dia 25: o enfermeiro via o
 * historico do dia errado e nenhum evento do dia que pediu.
 *
 * O backend compara com `ts_ms`, epoch absoluto — o limite certo e a
 * meia-noite local do usuario, que e o que o construtor por componentes da.
 */
export function limiteDoDiaLocal(valor: string, limite: 'inicio' | 'fim'): number | undefined {
  const partes = valor.split('-').map((p) => Number.parseInt(p, 10));
  if (partes.length !== 3 || partes.some((n) => !Number.isFinite(n))) {
    return undefined;
  }
  const [ano, mes, dia] = partes;
  return limite === 'inicio'
    ? new Date(ano, mes - 1, dia, 0, 0, 0, 0).getTime()
    : new Date(ano, mes - 1, dia, 23, 59, 59, 999).getTime();
}

const EVENT_TYPES = [
  { value: 'all', label: 'Todos os tipos' },
  { value: 'alert_open', label: 'Alerta criado' },
  { value: 'alert_acknowledged', label: 'Alerta reconhecido' },
  { value: 'alert_close', label: 'Alerta encerrado' },
  { value: 'repositioning', label: 'Reposicionamento' },
];

export function TimelinePage() {
  const { subscribe } = useWebSocketContext();
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  
  // Filters
  const [filters, setFilters] = useState<TimelineFilters>({
    limit: PAGE_SIZE,
  });
  const [tempFilters, setTempFilters] = useState<{
    paciente_id: string;
    tipo: string;
    dateFrom: string;
    dateTo: string;
  }>({
    paciente_id: '',
    tipo: 'all',
    dateFrom: '',
    dateTo: '',
  });

  const fetchPatients = async () => {
    try {
      const data = await patientsApi.getPatients();
      setPatients(data);
    } catch (err) {
      console.error('Error fetching patients:', err);
    }
  };

  const fetchEvents = useCallback(async () => {
    const loading = events.length === 0 ? setIsLoading : setIsRefreshing;
    loading(true);
    
    try {
      const data = await timelineApi.getEvents(filters);
      setEvents(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiException) {
        setError(err.message);
        toast.error(err.message);
      } else {
        setError('Erro ao carregar histórico');
        toast.error('Erro ao carregar histórico');
      }
    } finally {
      loading(false);
    }
  }, [filters, events.length]);

  useEffect(() => {
    fetchPatients();
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [filters]);

  useEffect(() => {
    const unsubscribe = subscribe(() => {
      fetchEvents();
    });
    return unsubscribe;
  }, [subscribe, fetchEvents]);

  const handleApplyFilters = () => {
    const newFilters: TimelineFilters = {
      limit: PAGE_SIZE,
    };

    if (tempFilters.paciente_id && tempFilters.paciente_id !== 'all') {
      newFilters.paciente_id = tempFilters.paciente_id;
    }

    if (tempFilters.tipo && tempFilters.tipo !== 'all') {
      newFilters.tipo = tempFilters.tipo;
    }

    if (tempFilters.dateFrom) {
      newFilters.start_ms = limiteDoDiaLocal(tempFilters.dateFrom, 'inicio');
    }

    if (tempFilters.dateTo) {
      newFilters.end_ms = limiteDoDiaLocal(tempFilters.dateTo, 'fim');
    }

    setFilters(newFilters);
    setShowFilters(false);
  };

  const handleClearFilters = () => {
    setTempFilters({
      paciente_id: '',
      tipo: 'all',
      dateFrom: '',
      dateTo: '',
    });
    setFilters({ limit: PAGE_SIZE });
  };

  const hasActiveFilters = 
    filters.paciente_id || 
    filters.tipo || 
    filters.start_ms || 
    filters.end_ms;

  const formatDateTime = (isoString: string) => {
    return new Date(isoString).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getRelativeTime = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days} dia${days > 1 ? 's' : ''} atrás`;
    if (hours > 0) return `${hours} hora${hours > 1 ? 's' : ''} atrás`;
    if (minutes > 0) return `${minutes} minuto${minutes > 1 ? 's' : ''} atrás`;
    return 'Agora mesmo';
  };

  const getEventIcon = (tipo: string) => {
    switch (tipo) {
      case 'alert_open':
        return <AlertCircle className="w-5 h-5 text-warning" />;
      case 'alert_acknowledged':
        return <Eye className="w-5 h-5 text-blue-500" />;
      case 'alert_completed':
      case 'alert_close':
        return <CheckCircle2 className="w-5 h-5 text-success" />;
      case 'repositioning':
        return <CheckCircle2 className="w-5 h-5 text-success" />;
      default:
        return <Clock className="w-5 h-5 text-muted-foreground" />;
    }
  };

  const getEventText = (tipo: string) => {
    switch (tipo) {
      case 'alert_open':
        return 'Alerta criado';
      case 'alert_acknowledged':
        return 'Alerta reconhecido';
      case 'alert_completed':
      case 'alert_close':
        return 'Alerta encerrado';
      case 'repositioning':
        return 'Paciente reposicionado';
      default:
        return tipo;
    }
  };

  const getEventBadge = (tipo: string) => {
    switch (tipo) {
      case 'alert_open':
        return (
          <Badge className="bg-warning text-warning-foreground">
            Alerta Aberto
          </Badge>
        );
      case 'alert_acknowledged':
        return (
          <Badge className="bg-blue-100 dark:bg-blue-900 text-blue-800 hover:bg-blue-200">
            Reconhecido
          </Badge>
        );
      case 'alert_completed':
      case 'alert_close':
        return (
          <Badge className="bg-success text-success-foreground">
            Encerrado
          </Badge>
        );
      case 'repositioning':
        return (
          <Badge className="bg-success text-success-foreground">
            Reposicionado
          </Badge>
        );
      default:
        return <Badge variant="outline">{tipo}</Badge>;
    }
  };

  // Group events by date
  const groupedEvents = events.reduce((acc, event) => {
    const date = new Date(event.ts).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    });
    if (!acc[date]) {
      acc[date] = [];
    }
    acc[date].push(event);
    return acc;
  }, {} as Record<string, TimelineEvent[]>);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Histórico de Eventos</h1>
            <p className="text-muted-foreground mt-1">Timeline de alertas e reposicionamentos</p>
          </div>
          <Skeleton className="h-10 w-32" />
        </div>
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex gap-4">
                  <Skeleton className="w-10 h-10 rounded-full flex-shrink-0" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-4 w-2/3" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Histórico de Eventos</h1>
          <p className="text-muted-foreground mt-1">
            Timeline de alertas e reposicionamentos
            {hasActiveFilters && ' • Filtros ativos'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchEvents()}
            disabled={isRefreshing}
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button
            variant={showFilters ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter className="w-4 h-4 mr-2" />
            Filtros
            {hasActiveFilters && (
              <Badge variant="secondary" className="ml-2">
                {Object.keys(filters).filter(k => k !== 'limit' && filters[k as keyof TimelineFilters]).length}
              </Badge>
            )}
          </Button>
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Filtros de Eventos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Patient Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-patient">Paciente</Label>
                <Select
                  value={tempFilters.paciente_id || 'all'}
                  onValueChange={(value: string) =>
                    setTempFilters((prev) => ({ ...prev, paciente_id: value === 'all' ? '' : value }))
                  }
                >
                  <SelectTrigger id="filter-patient">
                    <SelectValue placeholder="Todos os pacientes" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os pacientes</SelectItem>
                    {patients.map((patient) => (
                      <SelectItem key={patient.id} value={patient.id}>
                        {patient.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Event Type Filter */}
              <div className="space-y-2">
                <Label htmlFor="filter-type">Tipo de Evento</Label>
                <Select
                  value={tempFilters.tipo}
                  onValueChange={(value: string) =>
                    setTempFilters((prev) => ({ ...prev, tipo: value }))
                  }
                >
                  <SelectTrigger id="filter-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EVENT_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Date From */}
              <div className="space-y-2">
                <Label htmlFor="filter-date-from">Data Inicial</Label>
                <Input
                  type="date"
                  id="filter-date-from"
                  value={tempFilters.dateFrom}
                  onChange={(e) =>
                    setTempFilters((prev) => ({ ...prev, dateFrom: e.target.value }))
                  }
                />
              </div>

              {/* Date To */}
              <div className="space-y-2">
                <Label htmlFor="filter-date-to">Data Final</Label>
                <Input
                  type="date"
                  id="filter-date-to"
                  value={tempFilters.dateTo}
                  onChange={(e) =>
                    setTempFilters((prev) => ({ ...prev, dateTo: e.target.value }))
                  }
                />
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <Button onClick={handleApplyFilters} size="sm">
                <Filter className="w-4 h-4 mr-2" />
                Aplicar Filtros
              </Button>
              <Button onClick={handleClearFilters} variant="outline" size="sm">
                <X className="w-4 h-4 mr-2" />
                Limpar Filtros
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Export Panel */}
      <ExportPanel
        onSuccess={(msg) => toast.success(msg)}
        onError={(msg) => toast.error(msg)}
      />

      {/* Error Banner */}
      {error && (
        <ErrorBanner
          title="Erro"
          message={error}
          onRetry={fetchEvents}
          onDismiss={() => setError(null)}
        />
      )}

      {/* Events List */}
      {events.length === 0 && !error ? (
        <Card>
          <EmptyState
            icon={Clock}
            title="Nenhum evento registrado"
            description={
              hasActiveFilters
                ? 'Nenhum evento encontrado com os filtros aplicados. Tente ajustar os filtros.'
                : 'Os eventos de alertas e reposicionamentos aparecerão aqui'
            }
            action={
              hasActiveFilters
                ? {
                    label: 'Limpar Filtros',
                    onClick: handleClearFilters,
                  }
                : undefined
            }
          />
        </Card>
      ) : (
        <div className="space-y-6">
          {Object.entries(groupedEvents).map(([date, dayEvents]) => (
            <Card key={date}>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <CalendarIcon className="w-5 h-5 text-muted-foreground" />
                  <CardTitle className="text-lg">{date}</CardTitle>
                  <Badge variant="secondary">{dayEvents.length} evento{dayEvents.length !== 1 ? 's' : ''}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {dayEvents.map((event, index) => (
                    <div key={event.id} className="flex gap-4 pb-4 border-b last:border-b-0">
                      <div className="flex flex-col items-center">
                        <div className="bg-background border-2 rounded-full p-2 shadow-sm">
                          {getEventIcon(event.tipo)}
                        </div>
                        {index !== dayEvents.length - 1 && (
                          <div className="w-0.5 h-full bg-border mt-2" />
                        )}
                      </div>

                      <div className="flex-1 pt-1">
                        <div className="flex items-start justify-between gap-4 mb-2">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <h4 className="font-semibold text-foreground">
                                {getEventText(event.tipo)}
                              </h4>
                              {getEventBadge(event.tipo)}
                            </div>
                            <div className="space-y-1">
                              <p className="text-sm text-muted-foreground">
                                Paciente: <span className="font-medium text-foreground">
                                  {event.paciente_name || event.paciente_id}
                                </span>
                              </p>
                              {event.descricao && (
                                <p className="text-sm text-muted-foreground mt-1">
                                  {event.descricao}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="text-right text-sm text-muted-foreground whitespace-nowrap">
                            <p className="font-medium">{getRelativeTime(event.ts)}</p>
                            <p className="text-xs">{formatDateTime(event.ts)}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Load More Button
          O corte era comparado com 100 fixo, nao com o limite em vigor: depois
          de um "carregar mais" (limite 200) uma lista de 150 eventos — que ja e
          o historico completo — continuava exibindo o botao, e clicar nao
          mudava nada. Comparar com o limite pedido faz o botao aparecer so
          quando a resposta bateu no teto, ou seja, quando pode haver mais. */}
      {events.length >= (filters.limit ?? PAGE_SIZE) && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            onClick={() =>
              setFilters((prev) => ({ ...prev, limit: (prev.limit || PAGE_SIZE) + PAGE_SIZE }))
            }
            disabled={isRefreshing}
          >
            Carregar mais eventos
          </Button>
        </div>
      )}
    </div>
  );
}
