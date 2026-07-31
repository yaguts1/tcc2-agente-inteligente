/**
 * "Meus pacientes" — o interruptor entre olhar o próprio trabalho e a ala.
 *
 * Fica junto da tabela e não dentro do painel de filtros recolhível: não é um
 * filtro entre outros. É a decisão de "estou olhando meu trabalho ou o da ala",
 * feita várias vezes por plantão, e custar dois cliques a tornaria uma decisão
 * que ninguém toma — a pessoa fica na visão completa e volta a ler as trinta
 * linhas.
 *
 * Some quando não há nenhum leito assumido. Um interruptor que filtra para
 * zero é pior que ausente: quem o liga vê a lista vazia e conclui que o sistema
 * está quebrado, não que ainda não assumiu leito nenhum.
 */
import { ListChecks, Users } from 'lucide-react';
import { Button } from '../ui/button';

interface Props {
  soMeus: boolean;
  quantidade: number;
  onAlternar: () => void;
  onLiberarTodos: () => void | Promise<void>;
}

export function BarraDeTriagem({
  soMeus,
  quantidade,
  onAlternar,
  onLiberarTodos,
}: Props) {
  if (quantidade === 0 && !soMeus) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant={soMeus ? 'default' : 'outline'}
        size="toque"
        aria-pressed={soMeus}
        onClick={onAlternar}
      >
        {soMeus ? (
          <ListChecks className="w-4 h-4 mr-2" aria-hidden="true" />
        ) : (
          <Users className="w-4 h-4 mr-2" aria-hidden="true" />
        )}
        {soMeus ? `Meus leitos (${quantidade})` : `Ver só os meus (${quantidade})`}
      </Button>

      {quantidade > 0 && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => void onLiberarTodos()}
          // Fim de plantão. Sem este botão ninguém libera leito a leito, e as
          // atribuições ficariam vivas indefinidamente até "meus pacientes"
          // acumular o hospital inteiro e deixar de significar qualquer coisa.
          title="Libera todos os leitos que você assumiu — use ao sair do plantão"
        >
          Encerrar plantão
        </Button>
      )}
    </div>
  );
}
