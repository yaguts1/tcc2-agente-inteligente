/**
 * Lesões por pressão de um paciente — a variável de DESFECHO.
 *
 * O sistema media adesão ao reposicionamento e nunca registrava se a lesão
 * aconteceu. Sem esta tela o dado não tem por onde entrar, e sem o dado a
 * correlação que o projeto existe para demonstrar não é computável.
 *
 * Duas decisões de interface que vêm do modelo:
 *
 *  - **origem não tem valor pré-selecionado.** É a pergunta que separa
 *    prevalência (o paciente trouxe) de incidência (apareceu aqui), e um
 *    default decidiria por quem registra. É o oposto do motivo de encerramento
 *    de alerta, onde o caso comum vem marcado — ali a escolha frequente é
 *    óbvia, aqui as duas respostas são igualmente plausíveis e mudam o
 *    indicador;
 *
 *  - **o vocabulário vem do servidor.** Uma cópia da lista de sítios e estágios
 *    aqui seria o começo de duas listas divergentes — já aconteceu neste
 *    projeto com o intervalo por perfil de risco, onde o motor usava 60/90/120
 *    min e a tela dizia 2/3/4 h, o dobro.
 */
import { useEffect, useState } from 'react';
import {
  lesoesApi,
  ApiException,
  Lesao,
  VocabularioLesao,
} from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Skeleton } from '../ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { Spinner } from '../shared/Spinner';
import { Activity, Plus, X } from 'lucide-react';
import { toast } from 'sonner';

/** Rótulos legíveis. O conjunto de VALORES vem do servidor; aqui só a tradução. */
const ROTULOS: Record<string, string> = {
  presente_na_admissao: 'Presente na admissão',
  adquirida: 'Adquirida na unidade',
  estagio_1: 'Estágio 1',
  estagio_2: 'Estágio 2',
  estagio_3: 'Estágio 3',
  estagio_4: 'Estágio 4',
  nao_classificavel: 'Não classificável',
  tissular_profunda: 'Lesão tissular profunda',
  dispositivo_medico: 'Por dispositivo médico',
  membrana_mucosa: 'Em membrana mucosa',
  cicatrizada: 'Cicatrizada',
  alta_com_lesao: 'Alta com lesão',
  obito: 'Óbito',
  erro_de_registro: 'Erro de registro',
};

const rotulo = (valor: string | null) =>
  valor ? (ROTULOS[valor] ?? valor.replace(/_/g, ' ')) : '—';

interface Props {
  pacienteId: string;
  pacienteNome: string;
  onClose: () => void;
}

export function LesoesPanel({ pacienteId, pacienteNome, onClose }: Props) {
  const [lesoes, setLesoes] = useState<Lesao[]>([]);
  const [vocab, setVocab] = useState<VocabularioLesao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [form, setForm] = useState({ sitio: '', origem: '', estagio: '', observacoes: '' });

  const carregar = async () => {
    setCarregando(true);
    try {
      const [lista, vocabulario] = await Promise.all([
        lesoesApi.doPaciente(pacienteId),
        lesoesApi.vocabulario(),
      ]);
      setLesoes(lista);
      setVocab(vocabulario);
      setErro(null);
    } catch (e) {
      setErro(e instanceof ApiException ? e.message : 'Falha ao carregar lesões');
    } finally {
      setCarregando(false);
    }
  };

  useEffect(() => {
    void carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pacienteId]);

  const completo = form.sitio && form.origem && form.estagio;

  const registrar = async () => {
    if (!completo) return;
    setSalvando(true);
    try {
      await lesoesApi.registrar(pacienteId, {
        sitio: form.sitio,
        origem: form.origem,
        estagio: form.estagio,
        observacoes: form.observacoes.trim() || null,
      });
      toast.success('Lesão registrada');
      setForm({ sitio: '', origem: '', estagio: '', observacoes: '' });
      await carregar();
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : 'Falha ao registrar');
    } finally {
      setSalvando(false);
    }
  };

  const avaliar = async (lesao: Lesao, estagio: string) => {
    try {
      await lesoesApi.avaliar(lesao.id, { estagio });
      toast.success('Evolução registrada');
      await carregar();
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : 'Falha ao avaliar');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-foreground">
          <Activity className="w-5 h-5" aria-hidden="true" />
          Lesões — {pacienteNome}
        </h2>
        <Button variant="outline" size="sm" onClick={onClose} aria-label="Fechar">
          <X className="w-4 h-4" aria-hidden="true" />
        </Button>
      </div>

      {erro && <ErrorBanner message={erro} onRetry={carregar} />}

      <Card>
        <CardHeader>
          <CardTitle>Registrar lesão</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {carregando || !vocab ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="lesao-sitio">Sítio *</Label>
                  <Select
                    value={form.sitio}
                    onValueChange={(v) => setForm({ ...form, sitio: v })}
                    disabled={salvando}
                  >
                    <SelectTrigger id="lesao-sitio">
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      {vocab.sitios.map((s) => (
                        <SelectItem key={s} value={s}>
                          {rotulo(s)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="lesao-origem">Origem *</Label>
                  <Select
                    value={form.origem}
                    onValueChange={(v) => setForm({ ...form, origem: v })}
                    disabled={salvando}
                  >
                    <SelectTrigger id="lesao-origem">
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      {vocab.origens.map((o) => (
                        <SelectItem key={o} value={o}>
                          {rotulo(o)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/*
                    Sem valor pré-selecionado, e o aviso diz por quê: é a
                    resposta que decide se a lesão conta como resultado do
                    cuidado desta unidade.
                  */}
                  <p className="text-xs text-muted-foreground">
                    Só "adquirida na unidade" entra na taxa de incidência.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="lesao-estagio">Estágio *</Label>
                  <Select
                    value={form.estagio}
                    onValueChange={(v) => setForm({ ...form, estagio: v })}
                    disabled={salvando}
                  >
                    <SelectTrigger id="lesao-estagio">
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      {vocab.estagios.map((e) => (
                        <SelectItem key={e} value={e}>
                          {rotulo(e)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="lesao-obs">Observações</Label>
                <Input
                  id="lesao-obs"
                  value={form.observacoes}
                  onChange={(e) => setForm({ ...form, observacoes: e.target.value })}
                  disabled={salvando}
                />
              </div>

              <Button onClick={registrar} disabled={!completo || salvando}>
                {salvando ? <Spinner /> : <Plus className="w-4 h-4 mr-1" aria-hidden="true" />}
                Registrar
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {carregando ? (
        <Skeleton className="h-24 w-full" />
      ) : lesoes.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="Nenhuma lesão registrada"
          description="Registrar a ausência importa tanto quanto a presença: sem denominador e sem numerador, não há taxa."
        />
      ) : (
        <div className="space-y-3">
          {lesoes.map((lesao) => (
            <Card key={lesao.id}>
              <CardContent className="pt-6 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{rotulo(lesao.sitio)}</span>
                  <Badge variant={lesao.origem === 'adquirida' ? 'destructive' : 'secondary'}>
                    {rotulo(lesao.origem)}
                  </Badge>
                  <Badge variant="outline">{rotulo(lesao.estagio_atual)}</Badge>
                  {lesao.desfecho && <Badge variant="secondary">{rotulo(lesao.desfecho)}</Badge>}
                </div>

                {/*
                  Entrada e atual lado a lado: a TRAJETÓRIA é o dado clínico.
                  "Estágio 2 que cicatrizou" e "estágio 2 que virou 4" não são o
                  mesmo desfecho, e mostrar só o atual apagaria a diferença.
                */}
                {lesao.estagio_inicial !== lesao.estagio_atual && (
                  <p className="text-sm text-muted-foreground">
                    Entrou como {rotulo(lesao.estagio_inicial)} · {lesao.avaliacoes} avaliações
                  </p>
                )}

                {!lesao.desfecho && vocab && (
                  <div className="flex items-center gap-2 pt-2">
                    <Label htmlFor={`evolucao-${lesao.id}`} className="text-sm">
                      Reavaliar:
                    </Label>
                    <Select onValueChange={(v) => avaliar(lesao, v)}>
                      <SelectTrigger id={`evolucao-${lesao.id}`} className="w-56">
                        <SelectValue placeholder="Novo estágio" />
                      </SelectTrigger>
                      <SelectContent>
                        {vocab.estagios.map((e) => (
                          <SelectItem key={e} value={e}>
                            {rotulo(e)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
