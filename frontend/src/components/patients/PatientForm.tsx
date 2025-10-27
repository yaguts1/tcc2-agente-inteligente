import { useState } from 'react';
import { patientsApi, Patient, CreatePatientRequest, ApiException } from '../../lib/api';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Spinner } from '../shared/Spinner';
import { Alert, AlertDescription } from '../ui/alert';
import { AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { SimulationPanel } from './SimulationPanel';

interface PatientFormProps {
  patient?: Patient;
  onSuccess: () => void;
  onCancel: () => void;
}

export function PatientForm({ patient, onSuccess, onCancel }: PatientFormProps) {
  const [formData, setFormData] = useState<CreatePatientRequest>({
    name: patient?.name || '',
    room: patient?.room || '',
    bed: patient?.bed || '',
    riskLevel: patient?.riskLevel || 'medium',
    repositioningInterval: patient?.repositioningInterval || 2,
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSimulation, setShowSimulation] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      if (patient) {
        await patientsApi.updatePatient(patient.id, formData);
        toast.success('Paciente atualizado com sucesso');
        setShowSimulation(true); // Mostrar painel de simulação após edição
      } else {
        const newPatient = await patientsApi.createPatient(formData);
        toast.success('Paciente criado com sucesso');
        // Para novo paciente, salvar o ID antes de mostrar simulação
        patient = newPatient;
        setShowSimulation(true); // Mostrar painel de simulação após criação
      }
    } catch (err) {
      if (err instanceof ApiException) {
        setError(err.message);
      } else {
        setError('Erro ao salvar paciente');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSimulationSuccess = () => {
    toast.success('Dados simulados carregados na Timeline!');
  };

  return (
    <Card>
      <CardContent className="p-6">
        {showSimulation && patient ? (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-2">
                {patient.name}
              </h2>
              <p className="text-sm text-muted-foreground">
                Paciente criado/editado. Agora você pode simular dados para testes.
              </p>
            </div>

            <SimulationPanel
              patientId={patient.id}
              onSuccess={handleSimulationSuccess}
            />

            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setShowSimulation(false);
                onSuccess();
              }}
              className="w-full"
            >
              Voltar à Lista
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="name">Nome Completo *</Label>
              <Input
                id="name"
                type="text"
                placeholder="Digite o nome do paciente"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                disabled={isLoading}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="room">Quarto *</Label>
              <Input
                id="room"
                type="text"
                placeholder="ex: 201A"
                value={formData.room}
                onChange={(e) =>
                  setFormData({ ...formData, room: e.target.value })
                }
                disabled={isLoading}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="bed">Leito *</Label>
              <Input
                id="bed"
                type="text"
                placeholder="ex: Leito 1"
                value={formData.bed}
                onChange={(e) =>
                  setFormData({ ...formData, bed: e.target.value })
                }
                disabled={isLoading}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="riskLevel">Nível de Risco *</Label>
              <Select
                value={formData.riskLevel}
                onValueChange={(value: 'high' | 'medium' | 'low') =>
                  setFormData({ ...formData, riskLevel: value })
                }
                disabled={isLoading}
              >
                <SelectTrigger id="riskLevel">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Baixo Risco</SelectItem>
                  <SelectItem value="medium">Risco Médio</SelectItem>
                  <SelectItem value="high">Alto Risco</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="interval">Intervalo de Reposicionamento (horas) *</Label>
              <Input
                id="interval"
                type="number"
                min="1"
                max="24"
                step="0.5"
                placeholder="2"
                value={formData.repositioningInterval}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    repositioningInterval: parseFloat(e.target.value),
                  })
                }
                disabled={isLoading}
                required
              />
              <p className="text-muted-foreground">
                Tempo entre cada reposicionamento
              </p>
            </div>
          </div>

          <div className="flex gap-3 pt-4">
            <Button type="submit" disabled={isLoading} className="flex-1">
              {isLoading ? (
                <>
                  <Spinner size="sm" className="mr-2" />
                  Salvando...
                </>
              ) : patient ? (
                'Atualizar Paciente'
              ) : (
                'Criar Paciente'
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isLoading}
            >
              Cancelar
            </Button>
          </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
