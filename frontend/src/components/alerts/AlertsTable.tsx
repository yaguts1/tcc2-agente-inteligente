import { useState } from 'react';
import { Alert, BatchResult } from '../../lib/api';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Checkbox } from '../ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { CheckCircle2, AlertTriangle, Clock, Eye } from 'lucide-react';
import { EmptyState } from '../shared/EmptyState';
import { Skeleton } from '../ui/skeleton';
import { BulkActionBar } from './BulkActionBar';
import { useAlertSelection } from '../../hooks/useAlertSelection';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';

interface AlertsTableProps {
  alerts: Alert[];
  onAcknowledge: (alertId: string) => void;
  onComplete: (alertId: string) => void;
  /** Ações em lote. Usam o endpoint de lote, que reporta sucesso parcial. */
  onBulkAcknowledge: (alertIds: string[]) => Promise<BatchResult>;
  onBulkComplete: (alertIds: string[]) => Promise<BatchResult>;
  isLoading: boolean;
}

export function AlertsTable({
  alerts,
  onAcknowledge,
  onComplete,
  onBulkAcknowledge,
  onBulkComplete,
  isLoading,
}: AlertsTableProps) {
  const [confirmingComplete, setConfirmingComplete] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  
  // Initialize alert selection
  const {
    selectedIds,
    selectedCount,
    allSelected,
    isIndeterminate,
    toggleAlert,
    toggleAll,
    clearSelection,
    selecionarApenas,
  } = useAlertSelection(alerts.map((a) => a.id));

  const formatTime = (dateString: string) => {
    return new Date(dateString).toLocaleTimeString('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
    });
  };

  const getTimeUntil = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = date.getTime() - now.getTime();
    const minutes = Math.floor(Math.abs(diff) / 60000);
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;

    if (diff < 0) {
      if (hours > 0) {
        return `Atrasado ${hours}h ${mins}min`;
      }
      return `Atrasado ${mins}min`;
    } else {
      if (hours > 0) {
        return `Em ${hours}h ${mins}min`;
      }
      return `Em ${mins}min`;
    }
  };

  const isOverdue = (dateString: string) =>
    new Date(dateString) < new Date();

  const getRiskBadge = (level: string) => {
    switch (level) {
      case 'high':
        return <Badge variant="destructive">Alto Risco</Badge>;
      case 'medium':
        return (
          <Badge className="bg-warning text-warning-foreground">
            Risco Médio
          </Badge>
        );
      case 'low':
        return <Badge variant="secondary">Baixo Risco</Badge>;
      default:
        return null;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'acknowledged':
        return (
          <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-200">
            Reconhecido
          </Badge>
        );
      case 'pending':
        return <Badge variant="outline">Pendente</Badge>;
      default:
        return null;
    }
  };

  // `finally` aqui não é zelo: o AlertsContext RE-LANÇA o erro depois de
  // avisar o usuário. Sem ele, uma ação que falha deixa `processingId` preso —
  // o botão da linha fica desabilitado para sempre e a enfermeira não consegue
  // tentar de novo sem recarregar a página. No caso de concluir era pior: o
  // diálogo de confirmação também ficava aberto, sem responder.
  //
  // Os handlers de lote logo abaixo já faziam isso corretamente; os
  // individuais é que ficaram para trás.
  //
  // O `catch` vazio não é erro engolido: o AlertsContext já mostrou o toast
  // ANTES de re-lançar, e estes handlers são o fim da cadeia — o `onClick` não
  // aguarda a promise, então um erro que sobe daqui vira `unhandled rejection`
  // no console do navegador, sem nenhum destinatário. Absorver aqui, depois do
  // `finally` ter destravado a interface, é o comportamento correto.
  const semRelancar = (erro: unknown) => {
    // Mantém o rastro para depuração sem quebrar a página do usuário.
    console.error('[AlertsTable] acao falhou (usuario ja foi notificado):', erro);
  };

  const handleAcknowledgeClick = async (alertId: string) => {
    setProcessingId(alertId);
    try {
      await onAcknowledge(alertId);
    } catch (err) {
      semRelancar(err);
    } finally {
      setProcessingId(null);
    }
  };

  const handleCompleteClick = async (alertId: string) => {
    setProcessingId(alertId);
    try {
      await onComplete(alertId);
    } catch (err) {
      semRelancar(err);
    } finally {
      setProcessingId(null);
      setConfirmingComplete(null);
    }
  };

  // Ações em lote.
  //
  // Era `Promise.all(selectedIds.map(onAcknowledge))`: uma requisição por
  // alerta e, pior, `Promise.all` REJEITA no primeiro erro. Como o 409
  // `transicao_invalida` é um resultado esperado (outra pessoa já agiu sobre
  // aquele alerta), bastava um para o enfermeiro ver "erro" — enquanto os
  // demais já tinham sido gravados. A seleção ficava intacta e nada dizia
  // quais passaram, então repetir a ação era a única saída.
  //
  // O endpoint de lote responde `{processed, failed, errors[]}`. Os que
  // falharam continuam selecionados: o próximo clique repete exatamente o que
  // faltou, em vez de reprocessar o que já deu certo.
  const executarEmLote = async (
    acao: (ids: string[]) => Promise<BatchResult>
  ) => {
    setProcessingId('bulk');
    try {
      const resultado = await acao(selectedIds);
      if (resultado.failed === 0) {
        clearSelection();
        return;
      }
      // O backend só inclui `alert_id` quando sabe a qual alerta o erro
      // pertence; numa falha inesperada o item vem sem ele. Sem id não dá para
      // saber o que refazer, então a seleção fica como está — encolhê-la
      // sugeriria que o resto passou, que é justamente o que não se sabe.
      const idsQueFalharam = resultado.errors
        .map((e) => e.alert_id)
        .filter((id): id is string => Boolean(id));
      if (idsQueFalharam.length === resultado.failed) {
        selecionarApenas(idsQueFalharam);
      }
    } catch (err) {
      semRelancar(err);
    } finally {
      setProcessingId(null);
    }
  };

  const handleBulkAcknowledge = () => executarEmLote(onBulkAcknowledge);
  const handleBulkComplete = () => executarEmLote(onBulkComplete);

  const sortedAlerts = [...alerts].sort((a, b) => {
    const aOverdue = isOverdue(a.nextRepositioning);
    const bOverdue = isOverdue(b.nextRepositioning);

    if (aOverdue && !bOverdue) return -1;
    if (!aOverdue && bOverdue) return 1;

    return (
      new Date(a.nextRepositioning).getTime() -
      new Date(b.nextRepositioning).getTime()
    );
  });

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle2}
        title="Nenhum alerta ativo"
        // A frase anterior — "Todos os pacientes estão com reposicionamento em
        // dia" — AFIRMAVA algo que a tela não tem como saber: lista vazia é
        // igual quando está tudo bem e quando o sistema parou de receber
        // dados. Quem informa a diferença é o aviso de monitoramento no
        // Dashboard; aqui o texto apenas descreve o que de fato se sabe.
        description="Nenhum reposicionamento pendente no período. Confira o aviso de monitoramento acima para saber se há dados chegando."
      />
    );
  }

  return (
    <>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">
                <Checkbox
                  checked={isIndeterminate ? "indeterminate" : allSelected}
                  onCheckedChange={toggleAll}
                  aria-label="Selecionar todos os alertas"
                />
              </TableHead>
              <TableHead>Paciente</TableHead>
              <TableHead>Quarto/Leito</TableHead>
              <TableHead>Risco</TableHead>
              <TableHead>Último Reposic.</TableHead>
              <TableHead>Próximo Reposic.</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedAlerts.map((alert) => {
              const overdue = isOverdue(alert.nextRepositioning);
              const isProcessing = processingId === alert.id;
              const isSelected = selectedIds.includes(alert.id);

              return (
                <TableRow
                  key={alert.id}
                  className={`${overdue ? 'bg-danger-light/20' : ''} ${
                    isSelected ? 'bg-blue-50' : ''
                  }`}
                >
                  <TableCell>
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => toggleAlert(alert.id)}
                      aria-label={`Selecionar ${alert.patientName}`}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {overdue && (
                        <AlertTriangle className="w-4 h-4 text-danger flex-shrink-0" />
                      )}
                      <span className="truncate">{alert.patientName}</span>
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {alert.room} / {alert.bed}
                  </TableCell>
                  <TableCell>{getRiskBadge(alert.riskLevel)}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                      <div>
                        <div>{formatTime(alert.lastRepositioning)}</div>
                        <div className="text-muted-foreground">
                          {formatDate(alert.lastRepositioning)}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    <div className={overdue ? 'text-danger' : ''}>
                      <div>{formatTime(alert.nextRepositioning)}</div>
                      <div className="text-muted-foreground">
                        {getTimeUntil(alert.nextRepositioning)}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{getStatusBadge(alert.status)}</TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAcknowledgeClick(alert.id)}
                        disabled={alert.status === 'acknowledged' || isProcessing}
                      >
                        <Eye className="w-4 h-4 mr-1" />
                        Reconhecer
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => setConfirmingComplete(alert.id)}
                        disabled={isProcessing}
                      >
                        <CheckCircle2 className="w-4 h-4 mr-1" />
                        Reposicionar
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Confirmation Dialog */}
      <AlertDialog
        open={confirmingComplete !== null}
        onOpenChange={(open: boolean) => !open && setConfirmingComplete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar Reposicionamento</AlertDialogTitle>
            <AlertDialogDescription>
              Você confirma que o paciente foi reposicionado? Esta ação irá
              encerrar o alerta e registrar o evento.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                confirmingComplete && handleCompleteClick(confirmingComplete)
              }
            >
              Confirmar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk Action Bar */}
      {selectedCount > 0 && (
        <BulkActionBar
          selectedCount={selectedCount}
          isLoading={processingId === 'bulk'}
          onAcknowledgeAll={handleBulkAcknowledge}
          onCompleteAll={handleBulkComplete}
          onClearSelection={clearSelection}
        />
      )}
    </>
  );
}
