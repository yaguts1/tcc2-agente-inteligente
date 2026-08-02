/**
 * Calibração: a confiança que o sensor reporta prediz falso alarme?
 *
 * `grade.confianca` era gravada em toda amostra e nunca lida. O botão "falso
 * alarme" já existia no fechamento, então o dado do outro lado também já vinha
 * sendo coletado — faltava alguém somar os dois. Enquanto isso, "qual a taxa de
 * falso-positivo desta instalação?" só tinha uma resposta honesta: não sei.
 *
 * DUAS COISAS QUE ESTA TELA NÃO PODE SUAVIZAR
 * -------------------------------------------
 * 1. `taxa === null` significa "não sei", e não "zero por cento". Mostrar 0%
 *    onde não há dado convidaria alguém a afrouxar o limiar do filtro por causa
 *    de uma faixa vazia.
 * 2. O denominador anda junto do número, sempre. Com poucos alertas
 *    classificados qualquer taxa é ruído, e uma porcentagem grande e sozinha na
 *    tela é exatamente o que faz alguém mexer no limiar por causa de dois casos.
 */
import { useEffect, useState } from 'react';
import { calibracaoApi, ApiException, type Calibracao } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';

/** Abaixo disto, a taxa é ruído — e a tela diz isso em vez de deixar decidir. */
const MINIMO_PARA_CONFIAR = 20;

function percentual(taxa: number | null): string {
  return taxa === null ? '—' : `${(taxa * 100).toFixed(1)}%`;
}

export function CalibracaoPanel() {
  const [dados, setDados] = useState<Calibracao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [dias, setDias] = useState(30);

  useEffect(() => {
    let ativo = true;
    setDados(null);
    setErro(null);
    calibracaoApi
      .get(dias)
      .then((r) => ativo && setDados(r))
      .catch((e) =>
        ativo && setErro(e instanceof ApiException ? e.message : 'Falha ao carregar calibração'),
      );
    return () => {
      ativo = false;
    };
  }, [dias]);

  if (erro) return <ErrorBanner type="error" title="Erro" message={erro} />;
  if (!dados) return <Skeleton className="h-64 w-full" />;

  const poucos = dados.alertas_classificados < MINIMO_PARA_CONFIAR;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <CardTitle>Calibração do sensor</CardTitle>
        <label className="text-sm text-muted-foreground">
          Período{' '}
          <select
            className="ml-1 rounded border bg-background px-2 py-1"
            value={dias}
            onChange={(e) => setDias(Number(e.target.value))}
            aria-label="Período do relatório de calibração"
          >
            <option value={7}>7 dias</option>
            <option value={30}>30 dias</option>
            <option value={90}>90 dias</option>
          </select>
        </label>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-6">
          <div>
            <div className="text-3xl font-semibold">{percentual(dados.taxa_falso_alarme)}</div>
            <div className="text-sm text-muted-foreground">taxa de falso alarme</div>
          </div>
          <div>
            {/* O denominador ao lado do número, nunca escondido. */}
            <div className="text-3xl font-semibold">{dados.alertas_classificados}</div>
            <div className="text-sm text-muted-foreground">alertas classificados</div>
          </div>
        </div>

        {dados.alertas_classificados === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum alerta foi fechado <em>com motivo</em> neste período. A taxa de falso alarme só
            existe se a equipe disser quais alertas não deveriam ter existido — é o motivo
            &quot;falso alarme&quot; no diálogo de conclusão.
          </p>
        ) : (
          <>
            {poucos && (
              <p className="text-sm text-amber-600 dark:text-amber-500">
                Poucos alertas classificados ({dados.alertas_classificados}). Com este volume a taxa
                oscila muito — não vale mexer no limiar do filtro com base nela.
              </p>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">
                  Taxa de falso alarme por faixa de confiança do sensor
                </caption>
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4">Confiança</th>
                    <th className="py-2 pr-4">Alertas</th>
                    <th className="py-2 pr-4">Falsos</th>
                    <th className="py-2">Taxa</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.por_faixa.map((f) => (
                    <tr key={f.faixa} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-mono">{f.faixa}</td>
                      <td className="py-2 pr-4">{f.alertas}</td>
                      <td className="py-2 pr-4">{f.falsos}</td>
                      <td className="py-2">
                        {/* Faixa sem alerta mostra "—", não 0%. */}
                        {percentual(f.taxa)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-muted-foreground">
              A faixa de corte do filtro de qualidade é 0,80: amostras abaixo disso são
              descartadas antes de chegar ao motor. Se as faixas acima do corte errarem tanto
              quanto as de baixo, o problema não está no limiar.
              {dados.sem_amostras > 0 && (
                <>
                  {' '}
                  {dados.sem_amostras} alerta(s) ficaram fora do agrupamento por não terem mais as
                  amostras da janela (retenção), mas seguem contando na taxa global.
                </>
              )}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
