/**
 * O que estes testes protegem não é o layout — é a honestidade dos números.
 *
 * Um relatório de calibração que arredonda "não sei" para "0%" convida alguém a
 * afrouxar o limiar do filtro de qualidade por causa de uma faixa vazia. E uma
 * porcentagem grande sozinha na tela, sem o denominador, faz mexer no limiar por
 * causa de dois casos.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CalibracaoPanel } from './CalibracaoPanel';
import { calibracaoApi, type Calibracao } from '../../lib/api';

const BASE: Calibracao = {
  dias: 30,
  alertas_classificados: 0,
  falsos_alarmes: 0,
  taxa_falso_alarme: null,
  sem_amostras: 0,
  por_motivo: {},
  por_faixa: [
    { faixa: '<0.70', alertas: 0, falsos: 0, taxa: null },
    { faixa: '0.70-0.80', alertas: 0, falsos: 0, taxa: null },
    { faixa: '0.80-0.90', alertas: 0, falsos: 0, taxa: null },
    { faixa: '>=0.90', alertas: 0, falsos: 0, taxa: null },
  ],
};

function responder(parcial: Partial<Calibracao>) {
  vi.spyOn(calibracaoApi, 'get').mockResolvedValue({ ...BASE, ...parcial });
}

describe('CalibracaoPanel', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('sem dado, diz que não sabe — e não mostra 0%', async () => {
    responder({});
    render(<CalibracaoPanel />);

    expect(await screen.findByText('—')).toBeInTheDocument();
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument();
    expect(screen.getByText(/só existe se a equipe disser/i)).toBeInTheDocument();
  });

  it('faixa sem alerta mostra travessão, não zero por cento', async () => {
    responder({
      alertas_classificados: 30,
      falsos_alarmes: 3,
      taxa_falso_alarme: 0.1,
      por_faixa: [
        { faixa: '<0.70', alertas: 0, falsos: 0, taxa: null },
        { faixa: '0.70-0.80', alertas: 10, falsos: 0, taxa: 0 },
        { faixa: '0.80-0.90', alertas: 10, falsos: 1, taxa: 0.1 },
        { faixa: '>=0.90', alertas: 10, falsos: 2, taxa: 0.2 },
      ],
    });
    render(<CalibracaoPanel />);

    // A faixa vazia e a faixa com zero falsos NÃO podem ficar iguais: uma é
    // "não sei", a outra é "medi e deu zero".
    const linhaVazia = (await screen.findByText('<0.70')).closest('tr')!;
    expect(linhaVazia).toHaveTextContent('—');
    const linhaZero = screen.getByText('0.70-0.80').closest('tr')!;
    expect(linhaZero).toHaveTextContent('0.0%');
  });

  it('mostra o denominador junto da taxa', async () => {
    responder({ alertas_classificados: 40, falsos_alarmes: 4, taxa_falso_alarme: 0.1 });
    render(<CalibracaoPanel />);

    expect(await screen.findByText('10.0%')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText(/alertas classificados/i)).toBeInTheDocument();
  });

  it('avisa quando o volume é pequeno demais para decidir', async () => {
    responder({ alertas_classificados: 3, falsos_alarmes: 3, taxa_falso_alarme: 1 });
    render(<CalibracaoPanel />);

    // 100% com três casos não pode ser apresentado como conclusão.
    expect(await screen.findByText('100.0%')).toBeInTheDocument();
    expect(screen.getByText(/não vale mexer no limiar/i)).toBeInTheDocument();
  });

  it('não avisa de volume baixo quando há amostra suficiente', async () => {
    responder({ alertas_classificados: 120, falsos_alarmes: 12, taxa_falso_alarme: 0.1 });
    render(<CalibracaoPanel />);

    await screen.findByText('10.0%');
    expect(screen.queryByText(/não vale mexer no limiar/i)).not.toBeInTheDocument();
  });
});
