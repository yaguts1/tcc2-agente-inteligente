/**
 * Alternador de tema.
 *
 * O modo escuro estava escrito e não ligado: `globals.css` define
 * `@custom-variant dark` e o bloco inteiro de tokens `.dark`, e nada aplicava a
 * classe. O único `useTheme` do projeto vivia dentro de `ui/sonner.tsx`,
 * conectado a provider nenhum — então ele lia `system` como default e o valor
 * nunca mudava.
 *
 * Por que isto não é preferência estética aqui: uma ala às 03:00 recebia tela
 * branca no talo, num quarto escuro, com o paciente dormindo. A enfermeira
 * consulta o dashboard à beira do leito, e a tela é a única fonte de luz do
 * ambiente — o brilho acorda quem está sendo monitorado e destrói a adaptação
 * ao escuro de quem está trabalhando.
 *
 * Três estados, e não dois. "Sistema" é o default e resolve o caso comum sem
 * ninguém decidir nada: o tablet da ala noturna já está configurado em escuro
 * no SO. Mas a estação compartilhada frequentemente NÃO está, e quem entra no
 * plantão da noite precisa poder forçar — daí os dois estados explícitos.
 */
import { useTheme } from 'next-themes';
import { Monitor, Moon, Sun } from 'lucide-react';
import { Button } from '../ui/button';

const OPCOES = [
  { valor: 'light', rotulo: 'Claro', Icone: Sun },
  { valor: 'dark', rotulo: 'Escuro', Icone: Moon },
  { valor: 'system', rotulo: 'Sistema', Icone: Monitor },
] as const;

export function SeletorDeTema({ compacto = false }: { compacto?: boolean }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className="flex gap-1"
      role="radiogroup"
      aria-label="Tema da interface"
    >
      {OPCOES.map(({ valor, rotulo, Icone }) => {
        const ativo = theme === valor;
        return (
          <Button
            key={valor}
            type="button"
            variant={ativo ? 'default' : 'outline'}
            // `size` maior no modo não-compacto: o menu móvel é usado à beira
            // do leito, de luva, onde alvos pequenos não são acertados.
            size={compacto ? 'sm' : 'default'}
            role="radio"
            aria-checked={ativo}
            aria-label={rotulo}
            title={rotulo}
            onClick={() => setTheme(valor)}
          >
            <Icone className="w-4 h-4" aria-hidden="true" />
            {!compacto && <span className="ml-2">{rotulo}</span>}
          </Button>
        );
      })}
    </div>
  );
}
