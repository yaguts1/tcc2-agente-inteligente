import { useEffect, useState } from 'react';
import { deviceEventsApi, DeviceEvent, ApiException } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { Settings, RefreshCw, CheckCircle, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { Spinner } from '../shared/Spinner';

export function AdminPage() {
  const [events, setEvents] = useState<DeviceEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isReconciling, setIsReconciling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEvents();
  }, []);

  const fetchEvents = async () => {
    try {
      const data = await deviceEventsApi.getEvents();
      setEvents(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiException) {
        setError(err.message);
      } else {
        setError('Erro ao carregar eventos de dispositivos');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleReconcile = async () => {
    setIsReconciling(true);
    try {
      await deviceEventsApi.reconcile();
      toast.success('Reconciliação executada com sucesso');
      fetchEvents();
    } catch (err) {
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao executar reconciliação');
      }
    } finally {
      setIsReconciling(false);
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

  const pendingEvents = events.filter((e) => !e.processed_at);
  const processedEvents = events.filter((e) => e.processed_at);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-foreground">Administração</h1>
            <p className="text-muted-foreground">Gerenciar eventos de dispositivos</p>
          </div>
          <Skeleton className="h-10 w-40" />
        </div>
        <Card>
          <CardContent className="p-6">
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-foreground">Administração</h1>
          <p className="text-muted-foreground">
            Gerenciar eventos de dispositivos e reconciliação
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchEvents} disabled={isReconciling}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Atualizar
          </Button>
          <Button onClick={handleReconcile} disabled={isReconciling}>
            {isReconciling ? (
              <>
                <Spinner size="sm" className="mr-2" />
                Reconciliando...
              </>
            ) : (
              <>
                <CheckCircle className="w-4 h-4 mr-2" />
                Reconciliar
              </>
            )}
          </Button>
        </div>
      </div>

      {error && (
        <ErrorBanner
          title="Erro"
          message={error}
          onRetry={fetchEvents}
          onDismiss={() => setError(null)}
        />
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="bg-warning/10 p-2 rounded-lg">
              <Clock className="w-5 h-5 text-warning" />
            </div>
            <div>
              <p className="text-muted-foreground">Eventos Pendentes</p>
              <p className="text-foreground">{pendingEvents.length}</p>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="bg-success/10 p-2 rounded-lg">
              <CheckCircle className="w-5 h-5 text-success" />
            </div>
            <div>
              <p className="text-muted-foreground">Eventos Processados</p>
              <p className="text-foreground">{processedEvents.length}</p>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-3">
            <div className="bg-primary/10 p-2 rounded-lg">
              <Settings className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="text-muted-foreground">Total de Eventos</p>
              <p className="text-foreground">{events.length}</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Events Table */}
      <Card>
        <CardHeader>
          <CardTitle>Eventos de Dispositivos</CardTitle>
        </CardHeader>
        <CardContent>
          {events.length === 0 && !error ? (
            <EmptyState
              icon={Settings}
              title="Nenhum evento registrado"
              description="Eventos de dispositivos IoT aparecerão aqui"
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Dispositivo</TableHead>
                    <TableHead>Tipo de Evento</TableHead>
                    <TableHead>Dados</TableHead>
                    <TableHead>Criado em</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Processado em</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.map((event) => (
                    <TableRow key={event.id}>
                      <TableCell>#{event.id}</TableCell>
                      <TableCell className="font-mono text-sm">
                        {event.device_id}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{event.event_type}</Badge>
                      </TableCell>
                      <TableCell>
                        <code className="text-sm bg-muted px-2 py-1 rounded">
                          {JSON.stringify(event.event_data).substring(0, 50)}
                          {JSON.stringify(event.event_data).length > 50 && '...'}
                        </code>
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {formatDateTime(event.created_at)}
                      </TableCell>
                      <TableCell>
                        {event.processed_at ? (
                          <Badge className="bg-success text-success-foreground">
                            Processado
                          </Badge>
                        ) : (
                          <Badge className="bg-warning text-warning-foreground">
                            Pendente
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {event.processed_at
                          ? formatDateTime(event.processed_at)
                          : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
