/**
 * A escada de escalonamento na tela.
 *
 * O NÍVEL é decidido no servidor (`nucleo/escalonamento.py`, com testes por
 * propriedade). Aqui se verifica o que a tela faz com ele — que é onde a escada
 * ou muda o comportamento da equipe, ou não serve para nada.
 */
import { describe, expect, it } from 'vitest';
import type { Alert } from './api';
import {
  APARENCIA,
  ORDEM_ESCALONAMENTO,
  compararPorEscalonamento,
  tempoEmAberto,
} from './escalonamento';

function alerta(sobrescreve: Partial<Alert>): Alert {
  return {
    id: 'PAC-0001__2026-06-01T08:00:00',
    patientId: 'PAC-0001',
    patientName: 'Maria',
    room: '201',
    bed: 'A',
    lastRepositioning: '2026-06-01T07:00:00',
    nextRepositioning: '2026-06-01T08:00:00',
    riskLevel: 'high',
    status: 'pending',
    closureOrigin: null,
    closedBy: null,
    site: null,
    minutesOpen: 0,
    escalationLevel: 'normal',
    ...sobrescreve,
  };
}

describe('ordenação', () => {
  it('gravidade vem antes de risco do paciente', () => {
    // O ponto que a ordenação anterior errava. Ela ordenava só por atraso,
    // tratando todos os atrasos como comparáveis.
    //
    // Um alerta em VIOLAÇÃO num paciente de baixo risco não diz "este paciente
    // está em risco": diz "ninguém está respondendo nesta ala". Isso precisa
    // vir antes de um alerta recém-aberto em alto risco, que está sendo
    // atendido normalmente.
    const violacaoBaixoRisco = alerta({
      id: 'a',
      riskLevel: 'low',
      escalationLevel: 'violacao',
      minutesOpen: 400,
    });
    const novoAltoRisco = alerta({
      id: 'b',
      riskLevel: 'high',
      escalationLevel: 'normal',
      minutesOpen: 5,
    });

    expect([novoAltoRisco, violacaoBaixoRisco].sort(compararPorEscalonamento)[0].id).toBe(
      'a',
    );
  });

  it('dentro do mesmo nível, o mais antigo primeiro', () => {
    const antigo = alerta({ id: 'antigo', escalationLevel: 'critico', minutesOpen: 200 });
    const recente = alerta({ id: 'recente', escalationLevel: 'critico', minutesOpen: 130 });

    expect([recente, antigo].sort(compararPorEscalonamento).map((a) => a.id)).toEqual([
      'antigo',
      'recente',
    ]);
  });

  it('a ordenação é estável sob entradas iguais', () => {
    // Uma comparação que devolvesse valor não-zero para itens equivalentes
    // faria a lista reordenar sozinha a cada polling — e uma lista que se mexe
    // sob o dedo é como se marca o paciente errado.
    const a = alerta({ id: 'a', escalationLevel: 'atencao', minutesOpen: 70 });
    const b = alerta({ id: 'b', escalationLevel: 'atencao', minutesOpen: 70 });
    expect(compararPorEscalonamento(a, b)).toBe(0);
  });
});

describe('aparência', () => {
  it('normal não recebe destaque nenhum', () => {
    // Alerta recém-aberto já é um aviso por si. Dar cor a ele gastaria o
    // vocabulário visual no caso mais comum, e aí não sobra contraste para o
    // que de fato escalou.
    expect(APARENCIA.normal).toBeNull();
  });

  it('todo nível acima de normal é descrito por extenso, não só por cor', () => {
    // Cor sozinha é inacessível, e a tela é usada sob iluminação ruim de
    // madrugada por quem pode ter daltonismo.
    for (const nivel of ['atencao', 'critico', 'violacao'] as const) {
      expect(APARENCIA[nivel]?.rotulo).toBeTruthy();
      expect(APARENCIA[nivel]?.descricao).toBeTruthy();
    }
  });

  it('os tons claros trazem par escuro', () => {
    // Mesmo problema que custou uma passada inteira em 4.4: `bg-amber-100` sem
    // `dark:` vira uma faixa quase branca no tema escuro.
    for (const nivel of ['atencao', 'critico'] as const) {
      expect(APARENCIA[nivel]?.selo).toMatch(/dark:/);
    }
  });

  it('a ordem numérica bate com a gravidade', () => {
    expect(ORDEM_ESCALONAMENTO.normal).toBeLessThan(ORDEM_ESCALONAMENTO.atencao);
    expect(ORDEM_ESCALONAMENTO.atencao).toBeLessThan(ORDEM_ESCALONAMENTO.critico);
    expect(ORDEM_ESCALONAMENTO.critico).toBeLessThan(ORDEM_ESCALONAMENTO.violacao);
  });
});

describe('tempo em aberto', () => {
  it.each([
    [0, 'há 0min'],
    [45, 'há 45min'],
    [60, 'há 1h'],
    [125, 'há 2h05'],
    [260, 'há 4h20'],
  ])('%i minutos vira %s', (minutos, esperado) => {
    // "260 min" obriga quem lê a fazer a conta, e a conta não é feita — o
    // número vira ruído numa tela com 30 linhas.
    expect(tempoEmAberto(minutos)).toBe(esperado);
  });

  it('minuto negativo não vira texto absurdo', () => {
    // Relógio do cliente adiantado em relação ao servidor é comum, e produziria
    // "há -3min".
    expect(tempoEmAberto(-5)).toBe('há 0min');
  });

  it('o zero à esquerda existe', () => {
    // "há 2h5" se lê como duas horas e cinquenta.
    expect(tempoEmAberto(125)).toContain('05');
  });
});
