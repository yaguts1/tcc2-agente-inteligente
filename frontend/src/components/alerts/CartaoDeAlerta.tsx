/**
 * Um alerta como cartão, para telas abaixo de `lg`.
 *
 * A tela de alertas era uma tabela de 8 colunas dentro de `overflow-x-auto`.
 * No celular isso significa rolar HORIZONTALMENTE para alcançar os botões, que
 * eram `size="sm"` (32px) — bem abaixo do alvo de toque de 44px.
 *
 * O casco da aplicação já era responsivo (`AppLayout` tem menu móvel decente).
 * A superfície de trabalho não era: dava para navegar até a tela de alertas no
 * celular e não dava para USÁ-LA. E é a tela que a enfermagem abre à beira do
 * leito, de luva, frequentemente com uma mão só.
 *
 * Decisões que vêm do uso, não do layout:
 *
 *  - **leito primeiro, em destaque.** Numa ala de 30 leitos, quem está com o
 *    aparelho na mão está indo ATÉ um quarto. O nome confirma que se chegou no
 *    paciente certo; o leito é o que se procura;
 *
 *  - **o sítio anatômico fica junto do nome, não escondido.** "Trocânter D" diz
 *    para qual lado virar. Um alerta que só diz "vire o paciente" interrompe
 *    sem orientar;
 *
 *  - **as duas ações ocupam a largura toda, lado a lado.** Empilhá-las obrigaria
 *    a rolar para alcançar a segunda; encolhê-las traria de volta o alvo
 *    pequeno. Metade da largura de um celular ainda é muito mais que 44px.
 */
import { AlertTriangle, CheckCircle2, Clock, Eye } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Checkbox } from '../ui/checkbox';
import { Spinner } from '../shared/Spinner';

interface Props {
  alerta: {
    id: string;
    patientName: string;
    room: string | null;
    bed: string | null;
    riskLevel: string;
    status: string;
    lastRepositioning: string;
    nextRepositioning: string;
    site: string | null;
  };
  atrasado: boolean;
  selecionado: boolean;
  processando: boolean;
  rotuloDeSitio: (site: string | null) => string | null;
  selo: { risco: React.ReactNode; status: React.ReactNode };
  tempo: { proximo: string; restante: string; ultimo: string };
  onSelecionar: () => void;
  onReconhecer: () => void;
  onReposicionar: () => void;
}

export function CartaoDeAlerta({
  alerta,
  atrasado,
  selecionado,
  processando,
  rotuloDeSitio,
  selo,
  tempo,
  onSelecionar,
  onReconhecer,
  onReposicionar,
}: Props) {
  const sitio = rotuloDeSitio(alerta.site);
  const leito = [alerta.room, alerta.bed].filter(Boolean).join(' / ') || '—';

  return (
    <Card
      className={
        atrasado
          ? 'border-danger/60 bg-danger-light/20'
          : selecionado
            ? 'bg-blue-50 dark:bg-blue-950'
            : ''
      }
    >
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start gap-3">
          {/*
            A caixa de seleção ganha área de toque própria (`p-2 -m-2`): o
            controle desenhado tem 16px, e acertá-lo de luva ao lado de um botão
            de ação é como marcar o paciente errado por um milímetro.
          */}
          <label className="p-2 -m-2 cursor-pointer">
            <Checkbox
              checked={selecionado}
              onCheckedChange={onSelecionar}
              aria-label={`Selecionar ${alerta.patientName}`}
            />
          </label>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {atrasado && (
                <AlertTriangle
                  className="w-5 h-5 text-danger flex-shrink-0"
                  aria-hidden="true"
                />
              )}
              {/* O leito é o que se procura andando pela ala. */}
              <span className="font-semibold text-lg truncate">{leito}</span>
            </div>
            <p className="text-sm text-muted-foreground truncate">
              {alerta.patientName}
            </p>
            {sitio && (
              <p className="text-sm font-medium mt-1">{sitio}</p>
            )}
          </div>

          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            {selo.risco}
            {selo.status}
          </div>
        </div>

        <div className="flex items-center gap-2 text-sm">
          <Clock className="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true" />
          <span className={atrasado ? 'text-danger font-medium' : ''}>
            {tempo.proximo} · {tempo.restante}
          </span>
          <span className="text-muted-foreground ml-auto text-xs">
            último {tempo.ultimo}
          </span>
        </div>

        <div className="flex gap-2">
          <Button
            size="toque"
            variant="outline"
            className="flex-1"
            onClick={onReconhecer}
            disabled={alerta.status === 'acknowledged' || processando}
          >
            {processando ? (
              <Spinner />
            ) : (
              <Eye className="w-4 h-4 mr-2" aria-hidden="true" />
            )}
            Reconhecer
          </Button>
          <Button
            size="toque"
            className="flex-1"
            onClick={onReposicionar}
            disabled={processando}
          >
            <CheckCircle2 className="w-4 h-4 mr-2" aria-hidden="true" />
            Reposicionar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
