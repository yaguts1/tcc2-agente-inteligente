import { useEffect, useState } from 'react';
import {
  patientsApi,
  unitsApi,
  Patient,
  CreatePatientRequest,
  ApiException,
  PerfisRisco,
  Unit,
} from '../../lib/api';
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
  onSuccess: () => void | Promise<void>;
  onCancel: () => void;
}

export function PatientForm({ patient, onSuccess, onCancel }: PatientFormProps) {
  const [formData, setFormData] = useState<CreatePatientRequest>({
    name: patient?.name || '',
    room: patient?.room || '',
    bed: patient?.bed || '',
    riskLevel: patient?.riskLevel || 'medium',
  });
  // Intervalo por nivel de risco, vindo do BACKEND (mesma configuracao do
  // motor de alertas). Antes o formulario assumia 2h fixo, que so por acaso
  // batia com algum perfil — e nao batia com o motor.
  const [perfis, setPerfis] = useState<PerfisRisco | null>(null);
  // Unidades que ESTE usuário enxerga. Com uma ala só a lista tem um item e o
  // seletor nem aparece — a instalação de ala única não ganha um passo novo.
  const [unidades, setUnidades] = useState<Unit[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSimulation, setShowSimulation] = useState(false);
  const [createdPatient, setCreatedPatient] = useState<Patient | null>(null);

  useEffect(() => {
    patientsApi.getPerfisRisco().then(setPerfis).catch(() => setPerfis(null));
    unitsApi
      .list()
      .then((lista) => {
        setUnidades(lista);
        // Pré-seleciona quando só há uma opção: obrigar a escolher entre um
        // item é ruído, e deixar vazio faria a admissão cair na unidade padrão
        // sem ninguém decidir.
        if (lista.length === 1) {
          setFormData((atual) => ({ ...atual, unitId: lista[0].id }));
        }
      })
      .catch(() => setUnidades([]));
  }, []);

  const intervaloDoPerfil = perfis?.[formData.riskLevel as keyof PerfisRisco];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      if (patient) {
        console.log('[PatientForm] Updating patient:', patient.id);
        await patientsApi.updatePatient(patient.id, formData);
        console.log('[PatientForm] Patient updated successfully');
        toast.success('Paciente atualizado com sucesso');
        setShowSimulation(true);
      } else {
        console.log('[PatientForm] Creating new patient with data:', formData);
        const newPatient = await patientsApi.createPatient(formData);
        console.log('[PatientForm] Patient created successfully:', newPatient);
        toast.success('Paciente criado com sucesso');
        setCreatedPatient(newPatient);
        setShowSimulation(true);
      }
    } catch (err) {
      console.error('[PatientForm] Error saving patient:', err);
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
    console.log('[PatientForm] Simulation completed, calling onSuccess()');
    toast.success('Dados simulados carregados na Timeline!');
  };

  // Use createdPatient if we just created one, otherwise use the prop
  const displayPatient = createdPatient || patient;

  return (
    <Card>
      <CardContent className="p-6">
        {showSimulation && displayPatient ? (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-2">
                {displayPatient.name}
              </h2>
              <p className="text-sm text-muted-foreground">
                Paciente criado/editado. Agora você pode simular dados para testes.
              </p>
            </div>

            <SimulationPanel
              patientId={displayPatient.id}
              onSuccess={handleSimulationSuccess}
            />

            <Button
              type="button"
              variant="outline"
              onClick={async () => {
                console.log('[PatientForm] "Voltar à Lista" clicked, calling onSuccess()');
                setShowSimulation(false);
                await onSuccess();
                console.log('[PatientForm] onSuccess() completed');
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

            {/*
              Unidade só na ADMISSÃO. Ao editar, o seletor não aparece: mudar
              de ala é transferência, que reinicia o motor de alertas porque ser
              erguido para a maca é alívio de pressão real. Deixar isso num
              campo de formulário faria a mudança acontecer sem que o motor
              soubesse — o defeito que a transferência veio corrigir.

              Com uma ala só, o seletor some: instalação de ala única não ganha
              um passo a mais por causa de um recurso que ela não usa.
            */}
            {!patient && unidades.length > 1 && (
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="unitId">Unidade *</Label>
                <Select
                  value={formData.unitId ? String(formData.unitId) : ''}
                  onValueChange={(value) =>
                    setFormData({ ...formData, unitId: Number(value) })
                  }
                  disabled={isLoading}
                >
                  <SelectTrigger id="unitId">
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
                <p className="text-xs text-muted-foreground">
                  O mesmo número de leito pode existir em alas diferentes.
                </p>
              </div>
            )}

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

            {/*
              Campo somente-leitura, e não por simplificação: o intervalo é
              DERIVADO do perfil de risco (a mesma configuração que o motor de
              alertas usa para disparar). O backend nunca leu este valor —
              `create_patient` e `update_patient` sempre o descartaram. Ou seja,
              o campo era editável, o valor era enviado e nada acontecia: quem
              alterasse acreditaria ter mudado o protocolo do paciente sem ter
              mudado coisa alguma.

              Para mudar o intervalo, muda-se o perfil de risco (ou a
              configuração da instalação).
            */}
            <div className="space-y-2">
              <Label htmlFor="interval">Intervalo de Reposicionamento</Label>
              <Input
                id="interval"
                type="text"
                readOnly
                aria-describedby="interval-ajuda"
                value={intervaloDoPerfil ? `${intervaloDoPerfil}h` : '—'}
                className="bg-muted"
              />
              <p id="interval-ajuda" className="text-muted-foreground">
                Definido pelo perfil de risco selecionado acima — é o mesmo
                intervalo que dispara os alertas.
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
