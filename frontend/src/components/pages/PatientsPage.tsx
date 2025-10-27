import { useEffect, useState } from 'react';
import { patientsApi, Patient, ApiException } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { Users, Plus, Edit, Trash2 } from 'lucide-react';
import { PatientForm } from '../patients/PatientForm';
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

  useEffect(() => {
    fetchPatients();
  }, []);

  const fetchPatients = async () => {
    try {
      const data = await patientsApi.getPatients();
      setPatients(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiException) {
        setError(err.message);
      } else {
        setError('Erro ao carregar pacientes');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (patient: Patient) => {
    try {
      await patientsApi.deletePatient(patient.id);
      toast.success('Paciente removido com sucesso');
      setDeletingPatient(null);
      fetchPatients();
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
          onSuccess={() => {
            setShowForm(false);
            setEditingPatient(null);
            fetchPatients();
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
            <Card key={i}>
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
              <Card key={patient.id}>
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
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      onClick={() => setEditingPatient(patient)}
                    >
                      <Edit className="w-4 h-4 mr-1" />
                      Editar
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setDeletingPatient(patient)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={deletingPatient !== null}
        onOpenChange={(open) => !open && setDeletingPatient(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar Exclusão</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover o paciente{' '}
              <strong>{deletingPatient?.name}</strong>? Esta ação não pode ser
              desfeita.
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
