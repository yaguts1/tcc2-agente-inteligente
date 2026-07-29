import { useEffect, useState } from 'react';
import { patientsApi, unitsApi, Patient, Unit, ApiException } from '../../lib/api';
import { getStoredUser } from '../../lib/storage';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { Users, Plus, Edit, Trash2, Calendar, X, LogOut, ArrowRightLeft, Activity, ClipboardList } from 'lucide-react';
import { PatientForm } from '../patients/PatientForm';
import { AgendaPanel } from '../patients/AgendaPanel';
import { LesoesPanel } from '../patients/LesoesPanel';
import { BradenPanel } from '../patients/BradenPanel';
import { toast } from 'sonner';
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

export function PatientsPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingPatient, setEditingPatient] = useState<Patient | null>(null);
  const [deletingPatient, setDeletingPatient] = useState<Patient | null>(null);
  const [selectedPatientForAgenda, setSelectedPatientForAgenda] = useState<Patient | null>(null);
  const [pacienteDasLesoes, setPacienteDasLesoes] = useState<Patient | null>(null);
  const [pacienteDoBraden, setPacienteDoBraden] = useState<Patient | null>(null);
  // Nome das alas, para o cartão não mostrar um id cru. Só é exibido quando há
  // mais de uma: com ala única o rótulo seria ruído constante.
  const [unidades, setUnidades] = useState<Unit[]>([]);
  const [dandoAlta, setDandoAlta] = useState<Patient | null>(null);
  const [motivoAlta, setMotivoAlta] = useState('');
  const [transferindo, setTransferindo] = useState<Patient | null>(null);
  const [destino, setDestino] = useState<{ room: string; bed: string; unitId: number | null }>({
    room: '',
    bed: '',
    unitId: null,
  });
  const [emAcao, setEmAcao] = useState(false);

  // Só afordância de UI: quem decide é o backend, que exige o papel `admin`
  // vindo do JWT assinado. Esconder o botão evita oferecer uma ação que
  // responderia 403 — não é, e não pode ser confundido com, autorização.
  const ehAdmin = getStoredUser()?.role === 'admin';

  // O mesmo número de leito pode existir em alas diferentes, então sem o nome
  // da unidade "Leito 12" é ambíguo na tela de quem enxerga mais de uma.
  const nomeDaUnidade = (unitId: number | null) =>
    unidades.find((u) => u.id === unitId)?.nome ?? '—';

  useEffect(() => {
    unitsApi.list().then(setUnidades).catch(() => setUnidades([]));
  }, []);

  const fetchPatients = async () => {
    try {
      console.log('[PatientsPage] fetchPatients() called');
      const data = await patientsApi.getPatients();
      console.log('[PatientsPage] API returned patients:', data);
      setPatients(data);
      setError(null);
    } catch (err) {
      console.error('[PatientsPage] Error fetching patients:', err);
      if (err instanceof ApiException) {
        setError(err.message);
      } else {
        setError('Erro ao carregar pacientes');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPatients();
  }, []);

  const handleAlta = async (patient: Patient) => {
    setEmAcao(true);
    try {
      const r = await patientsApi.discharge(patient.id, motivoAlta.trim() || undefined);
      // A permanência vai no toast porque é o número que a alta produz e que
      // some da tela em seguida — o paciente sai da lista.
      toast.success(
        `Alta de ${patient.name} registrada — ${r.permanencia_horas}h de internação`,
      );
      setDandoAlta(null);
      setMotivoAlta('');
      await fetchPatients();
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : 'Falha ao dar alta');
    } finally {
      setEmAcao(false);
    }
  };

  const handleTransferencia = async (patient: Patient) => {
    setEmAcao(true);
    try {
      const r = await patientsApi.transfer(
        patient.id,
        destino.room.trim(),
        destino.bed.trim(),
        destino.unitId,
      );
      // Mudar de ala tira o paciente da lista de quem transferiu, e isso
      // precisa ser dito: um paciente que some sem explicação parece erro.
      toast.success(
        r.mudou_de_unidade
          ? `${patient.name} transferido para ${nomeDaUnidade(r.unidade_atual)} — sai desta lista`
          : `${patient.name}: ${r.cama_anterior ?? '—'} → ${r.cama_atual ?? '—'}`,
      );
      setTransferindo(null);
      setDestino({ room: '', bed: '', unitId: null });
      await fetchPatients();
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : 'Falha ao transferir');
    } finally {
      setEmAcao(false);
    }
  };

  const handleDelete = async (patient: Patient) => {
    try {
      const resultado = await patientsApi.deletePatient(patient.id);
      // O que foi apagado junto vai no toast. A exclusão leva o histórico
      // clínico inteiro (alertas, timeline, grade) e é irreversível — um
      // "removido com sucesso" genérico esconderia a diferença entre apagar
      // uma ficha recém-criada e apagar meses de acompanhamento.
      const historico =
        (resultado?.removidos?.alertas ?? 0) +
        (resultado?.removidos?.timeline_events ?? 0);
      toast.success(
        historico > 0
          ? `Paciente removido — ${historico} registros de histórico apagados`
          : 'Paciente removido com sucesso'
      );
      setDeletingPatient(null);
      await fetchPatients();
    } catch (err) {
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao remover paciente');
      }
    }
  };

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

  // Sub-view de Braden. `onSalvo` recarrega a lista porque a avaliação APLICA o
  // perfil na ficha — sem isso o cartão continuaria mostrando o risco antigo.
  if (pacienteDoBraden) {
    return (
      <BradenPanel
        pacienteId={pacienteDoBraden.id}
        pacienteNome={pacienteDoBraden.name}
        onClose={() => setPacienteDoBraden(null)}
        onSalvo={fetchPatients}
      />
    );
  }

  // Sub-view de lesões, no mesmo padrão da de agendas.
  if (pacienteDasLesoes) {
    return (
      <LesoesPanel
        pacienteId={pacienteDasLesoes.id}
        pacienteNome={pacienteDasLesoes.name}
        onClose={() => setPacienteDasLesoes(null)}
      />
    );
  }

  // Show AgendaPanel when patient is selected
  if (selectedPatientForAgenda) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-foreground">
              📅 Agendas - {selectedPatientForAgenda.name}
            </h1>
            <p className="text-muted-foreground">
              Gerencie as agendas de supressão, redução e monitoramento
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => setSelectedPatientForAgenda(null)}
          >
            <X className="w-4 h-4 mr-2" />
            Voltar
          </Button>
        </div>

        <AgendaPanel pacienteId={selectedPatientForAgenda.id} />
      </div>
    );
  }

  if (showForm || editingPatient) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-foreground">
              {editingPatient ? 'Editar Paciente' : 'Novo Paciente'}
            </h1>
            <p className="text-muted-foreground">
              Preencha as informações do paciente
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => {
              setShowForm(false);
              setEditingPatient(null);
            }}
          >
            Cancelar
          </Button>
        </div>

        <PatientForm
          patient={editingPatient || undefined}
          onSuccess={async () => {
            console.log('[PatientsPage] PatientForm.onSuccess() called');
            console.log('[PatientsPage] Calling fetchPatients() after form success');
            await fetchPatients();
            console.log('[PatientsPage] fetchPatients() completed, hiding form');
            setShowForm(false);
            setEditingPatient(null);
          }}
          onCancel={() => {
            setShowForm(false);
            setEditingPatient(null);
          }}
        />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-foreground">Pacientes</h1>
            <p className="text-muted-foreground">Gerenciar pacientes e riscos</p>
          </div>
          <Skeleton className="h-10 w-32" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <Card key={`skeleton-${i}`}>
              <CardContent className="p-6">
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-foreground">Pacientes</h1>
            <p className="text-muted-foreground">
              Gerenciar pacientes e níveis de risco
            </p>
          </div>
          <Button onClick={() => setShowForm(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Paciente
          </Button>
        </div>

        {error && (
          <ErrorBanner
            title="Erro"
            message={error}
            onRetry={fetchPatients}
            onDismiss={() => setError(null)}
          />
        )}

        {patients.length === 0 && !error ? (
          <Card>
            <EmptyState
              icon={Users}
              title="Nenhum paciente cadastrado"
              description="Comece adicionando pacientes para monitorar"
              action={{
                label: 'Adicionar Paciente',
                onClick: () => setShowForm(true),
              }}
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {patients.map((patient) => (
              <Card key={`patient-card-${patient.id}`}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="mb-2">{patient.name}</CardTitle>
                      {getRiskBadge(patient.riskLevel)}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 mb-4">
                    {unidades.length > 1 && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Unidade:</span>
                        <span className="text-foreground">
                          {nomeDaUnidade(patient.unitId)}
                        </span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Quarto:</span>
                      <span className="text-foreground">{patient.room}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Leito:</span>
                      <span className="text-foreground">{patient.bed}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Intervalo:</span>
                      <span className="text-foreground">
                        {patient.repositioningInterval}h
                      </span>
                    </div>
                  </div>
                  {/*
                    Duas fileiras, e a separação é deliberada.

                    Alta e transferência são o que a ala faz todo dia, e são as
                    ações que faltavam: até aqui a única forma de tirar um
                    paciente da tela era Excluir, que apaga alertas, timeline e
                    leituras de sensor. A enfermagem estava sendo empurrada para
                    o botão destrutivo por falta de alternativa.

                    Excluir desce para a fileira de baixo, junto das ações de
                    manutenção, e continua restrito a admin — é para erro de
                    cadastro, não para alta.
                  */}
                  <div className="flex gap-2 mb-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => {
                        // `?? ''` porque quarto e leito são opcionais: um
                        // paciente sem leito é caso válido, e passar `null`
                        // para o `value` do input o tornaria não-controlado.
                        setDestino({
                          room: patient.room ?? '',
                          bed: patient.bed ?? '',
                          unitId: patient.unitId,
                        });
                        setTransferindo(patient);
                      }}
                    >
                      <ArrowRightLeft className="w-4 h-4 mr-1" aria-hidden="true" />
                      Transferir
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => {
                        setMotivoAlta('');
                        setDandoAlta(patient);
                      }}
                    >
                      <LogOut className="w-4 h-4 mr-1" aria-hidden="true" />
                      Dar alta
                    </Button>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => setSelectedPatientForAgenda(patient)}
                    >
                      <Calendar className="w-4 h-4 mr-1" />
                      Agendas
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => setPacienteDasLesoes(patient)}
                    >
                      <Activity className="w-4 h-4 mr-1" aria-hidden="true" />
                      Lesões
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => setPacienteDoBraden(patient)}
                    >
                      <ClipboardList className="w-4 h-4 mr-1" aria-hidden="true" />
                      Braden
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => setEditingPatient(patient)}
                    >
                      <Edit className="w-4 h-4 mr-1" />
                      Editar
                    </Button>
                    {ehAdmin && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setDeletingPatient(patient)}
                        aria-label={`Excluir ${patient.name}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Alta */}
      <AlertDialog
        open={dandoAlta !== null}
        onOpenChange={(open: boolean) => !open && setDandoAlta(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Dar alta a {dandoAlta?.name}</AlertDialogTitle>
            <AlertDialogDescription>
              O leito <strong>{dandoAlta?.room}-{dandoAlta?.bed}</strong> fica livre
              e o paciente sai da lista da ala. O histórico clínico —
              alertas, linha do tempo e leituras de sensor —{' '}
              <strong>é preservado</strong>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <Label htmlFor="motivo-alta">Motivo (opcional)</Label>
            <Input
              id="motivo-alta"
              value={motivoAlta}
              placeholder="ex: melhora clínica, transferência externa"
              onChange={(e) => setMotivoAlta(e.target.value)}
              disabled={emAcao}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={emAcao}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                // `preventDefault` porque o Radix fecha o diálogo no clique da
                // ação: sem isso ele sumiria antes de a requisição responder, e
                // um erro do backend não teria onde aparecer.
                e.preventDefault();
                if (dandoAlta) void handleAlta(dandoAlta);
              }}
              disabled={emAcao}
            >
              {emAcao ? 'Registrando…' : 'Confirmar alta'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Transferência */}
      <AlertDialog
        open={transferindo !== null}
        onOpenChange={(open: boolean) => !open && setTransferindo(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Transferir {transferindo?.name}</AlertDialogTitle>
            <AlertDialogDescription>
              Sai de <strong>{transferindo?.room}-{transferindo?.bed}</strong>.
              A transferência conta como reposicionamento: o relógio da próxima
              virada recomeça agora, porque ser erguido para a maca é alívio de
              pressão real.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {/*
            Ala de destino só aparece com mais de uma. Transferir entre alas
            move o paciente para fora da lista de quem transferiu — daí o aviso
            no rodapé do seletor: um paciente que some sem explicação parece
            erro, e a pessoa refaria a operação.
          */}
          {unidades.length > 1 && (
            <div className="space-y-2">
              <Label htmlFor="destino-unidade">Unidade de destino</Label>
              <Select
                value={destino.unitId ? String(destino.unitId) : ''}
                onValueChange={(value) => setDestino({ ...destino, unitId: Number(value) })}
                disabled={emAcao}
              >
                <SelectTrigger id="destino-unidade">
                  <SelectValue placeholder="Selecione a ala" />
                </SelectTrigger>
                <SelectContent>
                  {unidades.map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>
                      {u.nome}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {destino.unitId !== null && destino.unitId !== transferindo?.unitId && (
                <p className="text-xs text-warning" role="alert">
                  Muda de ala: o paciente sai da sua lista.
                </p>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="destino-room">Quarto</Label>
              <Input
                id="destino-room"
                value={destino.room}
                onChange={(e) => setDestino({ ...destino, room: e.target.value })}
                disabled={emAcao}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="destino-bed">Leito</Label>
              <Input
                id="destino-bed"
                value={destino.bed}
                onChange={(e) => setDestino({ ...destino, bed: e.target.value })}
                disabled={emAcao}
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={emAcao}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                if (transferindo) void handleTransferencia(transferindo);
              }}
              disabled={emAcao || !destino.room.trim() || !destino.bed.trim()}
            >
              {emAcao ? 'Transferindo…' : 'Confirmar transferência'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={deletingPatient !== null}
        onOpenChange={(open: boolean) => !open && setDeletingPatient(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar Exclusão</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover o paciente{' '}
              <strong>{deletingPatient?.name}</strong>? Serão apagados também{' '}
              <strong>todo o histórico de alertas, a linha do tempo e as
              leituras de sensor</strong> deste paciente. Esta ação não pode ser
              desfeita.
              <br />
              <br />
              Para <strong>encerrar uma internação</strong>, use "Dar alta": o
              leito é liberado e o histórico fica preservado. Excluir é para erro
              de cadastro.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deletingPatient && handleDelete(deletingPatient)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
