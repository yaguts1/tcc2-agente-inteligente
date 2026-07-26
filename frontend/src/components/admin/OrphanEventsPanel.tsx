import { useEffect, useState } from 'react';
import { deviceEventsApi, BedStats, ApiException } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { RefreshCw, CheckCircle, AlertCircle, Bed, User, Calendar } from 'lucide-react';
import { toast } from 'sonner';
import { Spinner } from '../shared/Spinner';
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '../ui/alert';

export function OrphanEventsPanel() {
  const [bedStats, setBedStats] = useState<BedStats[]>([]);
  const [totalOrphans, setTotalOrphans] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [reconcilingBed, setReconcilingBed] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    try {
      const data = await deviceEventsApi.getStats();
      setBedStats(data.beds);
      setTotalOrphans(data.total_orphans);
      setError(null);
    } catch (err) {
      if (err instanceof ApiException) {
        setError(err.message);
      } else {
        setError('Erro ao carregar estatísticas');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const handleReconcileBed = async (camaId: string, patientName: string | null) => {
    if (!patientName) {
      toast.error(`Leito ${camaId} não possui paciente cadastrado`);
      return;
    }

    setReconcilingBed(camaId);
    try {
      const result = await deviceEventsApi.reconcileBed(camaId);
      
      if (result.error) {
        toast.error(result.error);
      } else {
        toast.success(
          `Reconciliado: ${result.processed} eventos para ${result.patient_name}`,
          { duration: 5000 }
        );
        await fetchStats();
      }
    } catch (err) {
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao reconciliar eventos');
      }
    } finally {
      setReconcilingBed(null);
    }
  };

  const formatDateTime = (isoString: string) => {
    return new Date(isoString).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <Card key={`skeleton-${i}`}>
              <CardContent className="p-6">
                <Skeleton className="h-32 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground">
          Reconcilie eventos recebidos antes do cadastro do paciente
        </p>
        <Button variant="outline" onClick={fetchStats}>
          <RefreshCw className="w-4 h-4 mr-2" />
          Atualizar
        </Button>
      </div>

      {error && (
        <ErrorBanner
          title="Erro"
          message={error}
          onRetry={fetchStats}
          onDismiss={() => setError(null)}
        />
      )}

      {totalOrphans > 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Eventos Órfãos Detectados</AlertTitle>
          <AlertDescription>
            Há <strong>{totalOrphans}</strong> eventos de {bedStats.length} leito(s) aguardando reconciliação.
            Estes eventos foram recebidos de ESP32s em leitos sem paciente cadastrado.
          </AlertDescription>
        </Alert>
      )}

      {bedStats.length === 0 ? (
        <Card>
          <EmptyState
            icon={CheckCircle}
            title="Nenhum evento órfão"
            description="Todos os eventos estão associados a pacientes"
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {bedStats.map((bed) => (
            <Card key={bed.cama_id} className="hover:shadow-md transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <CardTitle className="flex items-center gap-2 text-lg">
                      <Bed className="w-5 h-5" />
                      Leito {bed.cama_id}
                    </CardTitle>
                    <Badge variant="destructive" className="mt-2">
                      {bed.count} eventos órfãos
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="bg-muted/50 p-3 rounded-lg">
                  <div className="text-sm text-muted-foreground mb-1">
                    Paciente Atual:
                  </div>
                  {bed.current_patient ? (
                    <div className="flex items-center gap-2">
                      <User className="w-4 h-4" />
                      <span className="font-medium">{bed.current_patient.name}</span>
                    </div>
                  ) : (
                    <div className="text-muted-foreground italic">
                      Leito vazio
                    </div>
                  )}
                </div>

                <div className="space-y-1 text-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Calendar className="w-4 h-4" />
                    <span>Período dos eventos:</span>
                  </div>
                  <div className="pl-6">
                    <div>De: {formatDateTime(bed.first_event)}</div>
                    <div>Até: {formatDateTime(bed.last_event)}</div>
                  </div>
                </div>

                <div className="pt-2">
                  {bed.current_patient ? (
                    <Button
                      className="w-full"
                      onClick={() =>
                        handleReconcileBed(bed.cama_id, bed.current_patient?.name || null)
                      }
                      disabled={reconcilingBed === bed.cama_id}
                    >
                      {reconcilingBed === bed.cama_id ? (
                        <>
                          <Spinner className="w-4 h-4 mr-2" />
                          Reconciliando...
                        </>
                      ) : (
                        <>
                          <CheckCircle className="w-4 h-4 mr-2" />
                          Reconciliar para {bed.current_patient.name.split(' ')[0]}
                        </>
                      )}
                    </Button>
                  ) : (
                    <Alert>
                      <AlertDescription className="text-sm">
                        Cadastre um paciente neste leito para reconciliar
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card className="border-primary/40">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            Como Funciona a Reconciliação
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm space-y-2">
          <p>
            <strong>Eventos Órfãos</strong> são dados de ESP32s em leitos sem paciente.
          </p>
          <p>Acontece quando:</p>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li>ESP32 enviando dados antes do cadastro do paciente</li>
            <li>Atraso no cadastro após internação</li>
            <li>ESP32 em teste/manutenção</li>
          </ul>
          <p className="pt-2">
            Ao reconciliar, eventos órfãos são associados ao paciente atual e processados
            retroativamente (timeline + alertas).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
