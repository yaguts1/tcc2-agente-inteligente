import { useState } from 'react';
import { useSimulation } from '../../hooks/useSimulation';
import { SimulationRequest } from '../../lib/api';
import { getStoredUser } from '../../lib/storage';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Alert, AlertDescription } from '../ui/alert';
import { Spinner } from '../shared/Spinner';
import { AlertCircle, CheckCircle2, Play } from 'lucide-react';
import { toast } from 'sonner';

interface SimulationPanelProps {
  patientId: string;
  onSuccess?: (result: { eventos: number; alertas: number }) => void;
}

export function SimulationPanel({ patientId, onSuccess }: SimulationPanelProps) {
  const { isLoading, error, result, simulate, reset } = useSimulation(patientId);
  const [formData, setFormData] = useState<SimulationRequest>({
    duracao_horas: 24,
    seed: 42,
    perfil: 'medio',
  });

  // A simulação grava eventos, grade e alertas SINTÉTICOS no mesmo banco dos
  // dados reais, então o backend a restringe ao papel `admin`. Sem esta
  // checagem o painel apareceria para todo mundo e só falharia com 403 depois
  // que o usuário preenchesse o formulário e clicasse.
  const usuario = getStoredUser();
  if (usuario?.role !== 'admin') {
    return null;
  }

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      const result = await simulate(formData);
      toast.success(`✅ Simulação concluída! ${result.eventos} eventos e ${result.alertas} alertas gerados`);
      onSuccess?.(result);
    } catch (err) {
      // Erro já é tratado pelo hook
    }
  };

  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Play className="w-5 h-5" />
          Gerar Dados Simulados
        </CardTitle>
        <CardDescription>
          Gere dados de simulação para testar alertas e timeline
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {result && result.success ? (
          <div className="space-y-4">
            <Alert className="border-green-200 bg-green-50">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-800">
                ✅ Simulação concluída com sucesso!
              </AlertDescription>
            </Alert>

            <div className="grid grid-cols-2 gap-4 bg-muted p-4 rounded-lg">
              <div>
                <p className="text-sm text-muted-foreground">Duração</p>
                <p className="text-lg font-semibold">{result.duracao}h</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Eventos gerados</p>
                <p className="text-lg font-semibold text-blue-600">{result.eventos}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Alertas processados</p>
                <p className="text-lg font-semibold text-orange-600">{result.alertas}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <p className="text-lg font-semibold text-green-600">Concluído</p>
              </div>
            </div>

            <div className="text-sm text-muted-foreground">
              Verifique a Timeline para visualizar os eventos gerados.
            </div>

            <Button
              type="button"
              variant="outline"
              onClick={reset}
              className="w-full"
            >
              Gerar Novos Dados
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSimulate} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="duracao">Duração (horas) *</Label>
                <Input
                  id="duracao"
                  type="number"
                  min="1"
                  max="72"
                  placeholder="24"
                  value={formData.duracao_horas}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      duracao_horas: parseInt(e.target.value) || 24,
                    })
                  }
                  disabled={isLoading}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Mínimo 1h, máximo 72h (3 dias)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="seed">Seed (opcional)</Label>
                <Input
                  id="seed"
                  type="number"
                  placeholder="42"
                  value={formData.seed}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      seed: parseInt(e.target.value) || undefined,
                    })
                  }
                  disabled={isLoading}
                />
                <p className="text-xs text-muted-foreground">
                  Use para resultados reproduzíveis
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="perfil">Perfil de Risco *</Label>
                <Select
                  value={formData.perfil}
                  onValueChange={(value: 'baixo' | 'medio' | 'alto') =>
                    setFormData({ ...formData, perfil: value })
                  }
                  disabled={isLoading}
                >
                  <SelectTrigger id="perfil">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="baixo">
                      Baixo - Poucas transições de postura
                    </SelectItem>
                    <SelectItem value="medio">
                      Médio - Transições regulares (recomendado)
                    </SelectItem>
                    <SelectItem value="alto">
                      Alto - Muitas transições, maior risco
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button
              type="submit"
              disabled={isLoading}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Spinner size="sm" className="mr-2" />
                  Gerando dados ({formData.duracao_horas}h)...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  ▶️ Simular
                </>
              )}
            </Button>

            <p className="text-xs text-muted-foreground text-center">
              Isso gerará eventos de postura e alertas automaticamente.
              A simulação pode levar alguns segundos.
            </p>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
