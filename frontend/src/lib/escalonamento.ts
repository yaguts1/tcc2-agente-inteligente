/**
 * Como a escada de escalonamento aparece na tela.
 *
 * O NÍVEL vem do servidor (`nucleo/escalonamento.py`) — aqui só se decide como
 * ele é mostrado. A separação importa: a regra é clínica e o backend a usa para
 * decidir renotificar, então recalculá-la aqui criaria duas implementações que
 * divergem, e a divergência apareceria como "a tela diz crítico e o aviso não
 * toca".
 *
 * Um alerta aberto às 03:00 renderizava idêntico ao das 06:55. A única
 * diferença era um número maior no meio de uma linha de texto — que é
 * exatamente o tipo de informação que não é lida numa tela com 30 linhas.
 */
import type { Alert } from './api';

export type NivelEscalonamento = Alert['escalationLevel'];

export const ORDEM_ESCALONAMENTO: Record<NivelEscalonamento, number> = {
  normal: 0,
  atencao: 1,
  critico: 2,
  violacao: 3,
};

interface Aparencia {
  rotulo: string;
  /** Classe da LINHA/cartão. */
  destaque: string;
  /** Classe do selo. */
  selo: string;
  /** Descrito por extenso para leitor de tela — cor sozinha é inacessível. */
  descricao: string;
}

export const APARENCIA: Record<NivelEscalonamento, Aparencia | null> = {
  // `normal` não recebe nada. Um alerta recém-aberto já é um aviso por si; dar
  // cor a ele gastaria o vocabulário visual no caso mais comum, e aí não sobra
  // contraste para o que realmente escalou.
  normal: null,
  atencao: {
    rotulo: 'Atrasado',
    destaque: 'border-l-4 border-l-amber-500',
    selo: 'bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100',
    descricao: 'Uma janela inteira sem resposta',
  },
  critico: {
    rotulo: 'Crítico',
    destaque: 'border-l-4 border-l-danger',
    selo: 'bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100',
    descricao: 'Duas janelas sem resposta',
  },
  violacao: {
    rotulo: 'Violação',
    destaque: 'border-l-4 border-l-danger bg-danger-light/30',
    selo: 'bg-red-600 text-white',
    // A partir daqui o problema deixou de ser o paciente e passou a ser o
    // processo: alguém precisa saber que a ala não está conseguindo responder.
    descricao: 'Três janelas sem resposta — a ala não está respondendo',
  },
};

/**
 * "há 4h20" a partir dos minutos em aberto.
 *
 * Minutos crus (`260`) obrigam quem lê a fazer a conta, e a conta não é feita —
 * o número vira ruído. Horas e minutos são lidos de relance.
 */
export function tempoEmAberto(minutos: number): string {
  const total = Math.max(0, Math.round(minutos));
  if (total < 60) return `há ${total}min`;
  const horas = Math.floor(total / 60);
  const resto = total % 60;
  return resto === 0 ? `há ${horas}h` : `há ${horas}h${String(resto).padStart(2, '0')}`;
}

/**
 * Ordena por gravidade e, dentro do mesmo nível, pelo mais antigo.
 *
 * A ordenação anterior era só por atraso. Ela já era a ordenação certa em
 * espírito, mas tratava todos os atrasos como comparáveis — e não são: um
 * alerta em violação num paciente de baixo risco precisa vir antes de um recém
 * aberto em alto risco, porque o primeiro indica que ninguém está respondendo.
 */
export function compararPorEscalonamento(a: Alert, b: Alert): number {
  const diferenca =
    ORDEM_ESCALONAMENTO[b.escalationLevel] - ORDEM_ESCALONAMENTO[a.escalationLevel];
  return diferenca !== 0 ? diferenca : b.minutesOpen - a.minutesOpen;
}
