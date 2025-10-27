import { useEffect, useState } from 'react';
import { timelineApi, TimelineEvent, ApiException } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { ExportPanel } from '../ExportPanel';
import { CheckCircle2, Eye, AlertCircle, Clock } from 'lucide-react';
import { cn } from '../ui/utils';
import { toast } from 'sonner';

export function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEvents();
  }, []);

  const fetchEvents = async () => {
    try {
      const data = await timelineApi.getEvents();
      setEvents(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiException) {
        setError(err.message);
      } else {
        setError('Erro ao carregar histórico');
      }
    } finally {
      setIsLoading(false);
    }
  };

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
        return <Eye className="w-5 h-5 text-primary" />;
      case 'alert_completed':
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
          <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-200">
            Reconhecido
          </Badge>
        );
      case 'alert_completed':
      case 'repositioning':
        return (
          <Badge className="bg-success text-success-foreground">
            Completo
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
        <div>
          <h1 className="text-foreground">Histórico de Eventos</h1>
          <p className="text-muted-foreground">Timeline de alertas e reposicionamentos</p>
        </div>
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex gap-4">
                  <Skeleton className="w-10 h-10 rounded-full" />
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
      <div>
        <h1 className="text-foreground">Histórico de Eventos</h1>
        <p className="text-muted-foreground">
          Timeline de alertas e reposicionamentos
        </p>
      </div>

      {/* Export Panel */}
      <ExportPanel
        onSuccess={(msg) => toast.success(msg)}
        onError={(msg) => toast.error(msg)}
      />

      {error && (
        <ErrorBanner
          title="Erro"
          message={error}
          onRetry={fetchEvents}
          onDismiss={() => setError(null)}
        />
      )}

      {events.length === 0 && !error ? (
        <Card>
          <EmptyState
            icon={Clock}
            title="Nenhum evento registrado"
            description="Os eventos de alertas e reposicionamentos aparecerão aqui"
          />
        </Card>
      ) : (
        <div className="space-y-6">
          {Object.entries(groupedEvents).map(([date, dayEvents]) => (
            <Card key={date}>
              <CardHeader>
                <CardTitle>{date}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {dayEvents.map((event, index) => (
                    <div key={event.id} className="flex gap-4 pb-4 border-b last:border-b-0">
                      <div className="flex flex-col items-center">
                        <div className="bg-surface border-2 rounded-full p-2">
                          {getEventIcon(event.tipo)}
                        </div>
                        {index !== dayEvents.length - 1 && (
                          <div className="w-0.5 h-full bg-border mt-2" />
                        )}
                      </div>

                      <div className="flex-1 pt-1">
                        <div className="flex items-start justify-between gap-4 mb-2">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <h4 className="text-foreground">
                                {getEventText(event.tipo)}
                              </h4>
                              {getEventBadge(event.tipo)}
                            </div>
                            <p className="text-muted-foreground">
                              Paciente ID: {event.paciente_id}
                            </p>
                            {event.descricao && (
                              <p className="text-muted-foreground mt-1">
                                {event.descricao}
                              </p>
                            )}
                          </div>
                          <div className="text-right text-muted-foreground whitespace-nowrap">
                            <p>{getRelativeTime(event.ts)}</p>
                          </div>
                        </div>
                        <div className="text-muted-foreground">
                          <span>{formatDateTime(event.ts)}</span>
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
    </div>
  );
}
