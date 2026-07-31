/**
 * O aviso volta quando o alerta ESCALA — e só quando escala.
 *
 * Antes, o aviso disparava uma vez por alerta e nunca mais: um alerta aberto às
 * 03:00 avisava na hora em que abriu e depois se dissolvia no ruído até o turno
 * seguinte, mesmo atravessando duas e três janelas sem ninguém responder.
 *
 * Renotificar por MUDANÇA DE NÍVEL evita as duas falhas opostas, e as duas são
 * caras: repetir a cada N minutos treina a equipe a ignorar a categoria inteira
 * (é a razão dominante pela qual sistemas de alarme clínico são desligados), e
 * nunca repetir era o estado anterior.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import type { Alert } from '../lib/api';
import { useCriticalAlerts } from './useCriticalAlerts';

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

/**
 * Conta quantos AVISOS foram tocados.
 *
 * Dois detalhes que a primeira versao deste arquivo errou, os dois descobertos
 * rodando e nao lendo:
 *
 *  - contar a construcao do `AudioContext` daria sempre 1, porque ele fica num
 *    ref e e reusado entre avisos — o teste passaria sem verificar nada;
 *
 *  - cada aviso cria DOIS osciladores, porque o som e de dois tons (800 e
 *    1200 Hz). Contar oscilador daria o dobro, e a leitura natural do numero
 *    seria "esta avisando duas vezes".
 */
const TONS_POR_AVISO = 2;
let osciladores = 0;
const avisos = () => osciladores / TONS_POR_AVISO;

beforeEach(() => {
  osciladores = 0;
  // O beep usa WebAudio, que jsdom não implementa. O que interessa aqui é
  // QUANTAS VEZES ele é acionado, não o som.
  vi.stubGlobal(
    'AudioContext',
    vi.fn(() => {
      return {
        state: 'running',
        currentTime: 0,
        destination: {},
        resume: vi.fn(),
        close: vi.fn(),
        createOscillator: () => {
          osciladores += 1;
          return {
          connect: vi.fn(),
          start: vi.fn(),
          stop: vi.fn(),
          frequency: { setValueAtTime: vi.fn() },
          type: '',
          };
        },
        createGain: () => ({
          connect: vi.fn(),
          gain: {
            setValueAtTime: vi.fn(),
            exponentialRampToValueAtTime: vi.fn(),
          },
        }),
      };
    }),
  );
});

function montar(inicial: Alert[]) {
  return renderHook(
    ({ alerts }: { alerts: Alert[] }) =>
      useCriticalAlerts(alerts, { notificationsEnabled: false }),
    { initialProps: { alerts: inicial } },
  );
}

describe('renotificação', () => {
  it('avisa uma vez quando o alerta aparece', async () => {
    const { result } = montar([alerta({ escalationLevel: 'normal' })]);
    await act(async () => {});
    expect(result.current.criticalAlerts).toHaveLength(1);
    expect(avisos()).toBe(1);
  });

  it('NÃO avisa de novo se nada mudou', async () => {
    // O caso que quebra a confiança: a lista é recarregada por polling e por
    // WebSocket o tempo todo. Reavisar a cada atualização faria o beep tocar
    // continuamente enquanto um alerta estivesse aberto.
    const inicial = [alerta({ escalationLevel: 'atencao' })];
    const { rerender } = montar(inicial);
    await act(async () => {});
    const depoisDoPrimeiro = avisos();

    for (let i = 0; i < 3; i++) {
      rerender({ alerts: [alerta({ escalationLevel: 'atencao' })] });
      await act(async () => {});
    }

    expect(avisos()).toBe(depoisDoPrimeiro);
  });

  it('avisa de novo quando o nível SOBE', async () => {
    const { rerender } = montar([alerta({ escalationLevel: 'atencao' })]);
    await act(async () => {});
    const antes = avisos();

    rerender({ alerts: [alerta({ escalationLevel: 'critico' })] });
    await act(async () => {});

    expect(avisos()).toBeGreaterThan(antes);
  });

  it('não avisa quando o nível CAI', async () => {
    // Reconhecer trava a escada em `atencao` no servidor. A queda de nível é,
    // portanto, sinal de que alguém assumiu — o oposto de um motivo para
    // chamar atenção.
    const { rerender } = montar([alerta({ escalationLevel: 'critico' })]);
    await act(async () => {});
    const antes = avisos();

    rerender({
      alerts: [alerta({ escalationLevel: 'atencao', status: 'acknowledged' })],
    });
    await act(async () => {});

    expect(avisos()).toBe(antes);
  });

  it('no máximo três repetições na vida de um alerta', async () => {
    // A escada tem três degraus acima de normal. Um alerta ignorado a noite
    // inteira avisa quatro vezes no total, não a cada polling — é o teto que
    // torna a repetição tolerável.
    const niveis = ['normal', 'atencao', 'critico', 'violacao'] as const;
    const { rerender } = montar([alerta({ escalationLevel: 'normal' })]);
    await act(async () => {});

    for (const nivel of niveis.slice(1)) {
      // Várias atualizações por degrau, como acontece de verdade.
      for (let i = 0; i < 5; i++) {
        rerender({ alerts: [alerta({ escalationLevel: nivel })] });
        await act(async () => {});
      }
    }

    expect(avisos()).toBe(4);
  });
});
