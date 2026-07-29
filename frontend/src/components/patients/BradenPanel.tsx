/**
 * Escala de Braden de um paciente.
 *
 * O risco era um enum de três valores num dropdown — sem escore, sem subescores,
 * sem data de reavaliação, sem quem classificou — e as janelas de
 * reposicionamento eram variáveis de ambiente globais.
 *
 * Três decisões de interface que vêm do instrumento:
 *
 *  - **nenhum subescore vem pré-selecionado.** Um Braden com cinco dos seis
 *    campos não é um Braden, e um default faria o total colocar o paciente numa
 *    faixa MAIS LEVE que a real — o erro que mais importa evitar aqui;
 *
 *  - **o total e a janela resultante aparecem ANTES de salvar.** Sem isso, a
 *    relação entre o instrumento que a enfermeira preenche e o comportamento do
 *    sistema fica invisível, que era exatamente o estado anterior;
 *
 *  - **fricção/cisalhamento vai até 3, não 4.** A escala é assim. Os limites vêm
 *    do servidor, não de constantes daqui: aceitar 4 inflaria o total e poderia
 *    rebaixar o paciente de faixa sem ninguém perceber.
 */
import { useEffect, useState } from 'react';
import { bradenApi, ApiException, BradenAvaliacao, BradenEscala } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { Spinner } from '../shared/Spinner';
import { ClipboardList, Save, X } from 'lucide-react';
import { toast } from 'sonner';

const ROTULO_SUBESCALA: Record<string, string> = {
  percepcao_sensorial: 'Percepção sensorial',
  umidade: 'Umidade',
  atividade: 'Atividade',
  mobilidade: 'Mobilidade',
  nutricao: 'Nutrição',
  friccao_cisalhamento: 'Fricção e cisalhamento',
};

const ROTULO_FAIXA: Record<string, string> = {
  sem_risco: 'Sem risco',
  baixo: 'Risco baixo',
  moderado: 'Risco moderado',
  alto: 'Risco alto',
  muito_alto: 'Risco muito alto',
};

/** Intervalo de reposicionamento por perfil, só para exibição. */
const HORAS_POR_PERFIL: Record<string, string> = {
  alto: '1h',
  medio: '1,5h',
  baixo: '2h',
};

interface Props {
  pacienteId: string;
  pacienteNome: string;
  onClose: () => void;
  /** Chamado após salvar: o perfil do paciente muda, então a lista precisa recarregar. */
  onSalvo?: () => void | Promise<void>;
}

export function BradenPanel({ pacienteId, pacienteNome, onClose, onSalvo }: Props) {
  const [escala, setEscala] = useState<BradenEscala | null>(null);
  const [historico, setHistorico] = useState<BradenAvaliacao[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [valores, setValores] = useState<Record<string, number | null>>({});
  const [observacoes, setObservacoes] = useState('');

  const carregar = async () => {
    setCarregando(true);
    try {
      const [dados, lista] = await Promise.all([
        bradenApi.escala(),
        bradenApi.doPaciente(pacienteId),
      ]);
      setEscala(dados);
      setHistorico(lista);
      setErro(null);
    } catch (e) {
      setErro(e instanceof ApiException ? e.message : 'Falha ao carregar Braden');
    } finally {
      setCarregando(false);
    }
  };

  useEffect(() => {
    void carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pacienteId]);

  const nomes = escala ? Object.keys(escala.subescalas) : [];
  const completo = nomes.length > 0 && nomes.every((n) => valores[n] != null);
  const total = nomes.reduce((soma, n) => soma + (valores[n] ?? 0), 0);

  // A faixa é derivada no SERVIDOR; aqui só reproduzimos o mapeamento que ele
  // enviou, para mostrar o resultado antes de salvar.
  const faixaPrevista = (() => {
    if (!completo) return null;
    if (total <= 9) return 'muito_alto';
    if (total <= 12) return 'alto';
    if (total <= 14) return 'moderado';
    if (total <= 18) return 'baixo';
    return 'sem_risco';
  })();
  const perfilPrevisto = faixaPrevista ? escala?.perfil_por_faixa[faixaPrevista] : null;

  const salvar = async () => {
    if (!completo) return;
    setSalvando(true);
    try {
      const r = await bradenApi.registrar(pacienteId, {
        percepcao_sensorial: valores.percepcao_sensorial!,
        umidade: valores.umidade!,
        atividade: valores.atividade!,
        mobilidade: valores.mobilidade!,
        nutricao: valores.nutricao!,
        friccao_cisalhamento: valores.friccao_cisalhamento!,
        observacoes: observacoes.trim() || null,
      });
      toast.success(
        `Braden ${r.total} — ${ROTULO_FAIXA[r.faixa] ?? r.faixa}. ` +
          `Reposicionamento a cada ${HORAS_POR_PERFIL[r.perfil] ?? '—'}.`,
      );
      setValores({});
      setObservacoes('');
      await carregar();
      await onSalvo?.();
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : 'Falha ao salvar');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-foreground">
          <ClipboardList className="w-5 h-5" aria-hidden="true" />
          Braden — {pacienteNome}
        </h2>
        <Button variant="outline" size="sm" onClick={onClose} aria-label="Fechar">
          <X className="w-4 h-4" aria-hidden="true" />
        </Button>
      </div>

      {erro && <ErrorBanner message={erro} onRetry={carregar} />}

      <Card>
        <CardHeader>
          <CardTitle>Nova avaliação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {carregando || !escala ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {nomes.map((nome) => {
                  const { minimo, maximo } = escala.subescalas[nome];
                  const opcoes = Array.from(
                    { length: maximo - minimo + 1 },
                    (_, i) => minimo + i,
                  );
                  return (
                    <div key={nome} className="space-y-2">
                      <Label>
                        {ROTULO_SUBESCALA[nome] ?? nome}{' '}
                        <span className="text-xs text-muted-foreground">
                          ({minimo}–{maximo})
                        </span>
                      </Label>
                      {/*
                        Botões e não select: os valores são 1–4 (ou 1–3), cabem
                        na linha, e um select esconderia o intervalo — que é
                        justamente onde fricção difere das outras cinco.
                      */}
                      <div className="flex gap-1" role="radiogroup" aria-label={nome}>
                        {opcoes.map((v) => (
                          <Button
                            key={v}
                            type="button"
                            size="sm"
                            variant={valores[nome] === v ? 'default' : 'outline'}
                            aria-pressed={valores[nome] === v}
                            onClick={() => setValores({ ...valores, [nome]: v })}
                            disabled={salvando}
                          >
                            {v}
                          </Button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="space-y-2">
                <Label htmlFor="braden-obs">Observações</Label>
                <Input
                  id="braden-obs"
                  value={observacoes}
                  onChange={(e) => setObservacoes(e.target.value)}
                  disabled={salvando}
                />
              </div>

              {/*
                O total e a janela ANTES de salvar. Sem isto, a relação entre o
                instrumento preenchido e o comportamento do sistema fica
                invisível — o estado anterior, com o perfil num dropdown e as
                janelas em variável de ambiente.
              */}
              {completo && faixaPrevista && (
                <div className="rounded-md border p-3 text-sm" role="status">
                  Total <strong>{total}</strong> ·{' '}
                  {ROTULO_FAIXA[faixaPrevista] ?? faixaPrevista} · reposicionamento a cada{' '}
                  <strong>{HORAS_POR_PERFIL[perfilPrevisto ?? ''] ?? '—'}</strong>
                </div>
              )}
              {!completo && (
                <p className="text-xs text-muted-foreground">
                  Os seis subescores são obrigatórios: um Braden incompleto
                  colocaria o paciente numa faixa de risco mais leve que a real.
                </p>
              )}

              <Button onClick={salvar} disabled={!completo || salvando}>
                {salvando ? <Spinner /> : <Save className="w-4 h-4 mr-1" aria-hidden="true" />}
                Salvar avaliação
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {carregando ? (
        <Skeleton className="h-24 w-full" />
      ) : historico.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="Nenhuma avaliação registrada"
          description="Sem Braden, a janela de reposicionamento deste paciente não tem escore por trás."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Histórico</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {historico.map((a) => (
              <div
                key={a.id}
                className="flex flex-wrap items-center gap-2 border-b pb-2 last:border-b-0"
              >
                <span className="font-medium">{a.total}</span>
                <Badge variant={a.perfil === 'alto' ? 'destructive' : 'secondary'}>
                  {ROTULO_FAIXA[a.faixa] ?? a.faixa}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {a.avaliada_ts.replace('T', ' ')}
                  {a.avaliada_por ? ` · ${a.avaliada_por}` : ''}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
