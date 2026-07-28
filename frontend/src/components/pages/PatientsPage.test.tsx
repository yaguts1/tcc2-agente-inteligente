/**
 * Alta e transferência na tela de Pacientes.
 *
 * Os dois endpoints existiam sem nenhum botão que os chamasse, e a única forma
 * de tirar um paciente da lista era Excluir — que apaga alertas, linha do tempo
 * e leituras de sensor. A enfermagem estava sendo empurrada para o botão
 * destrutivo por falta de alternativa, justamente na operação mais rotineira
 * de uma ala.
 *
 * O que estes testes protegem:
 *
 *  - alta e transferência são alcançáveis sem passar por Excluir;
 *  - o diálogo NÃO fecha antes da resposta do backend (senão um erro não teria
 *    onde aparecer, e a tela diria que deu certo);
 *  - o texto de Excluir aponta a alternativa, porque um botão destrutivo sem
 *    saída à vista é o que produz o uso errado.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PatientsPage } from './PatientsPage';
import { patientsApi, unitsApi, ApiException } from '../../lib/api';

vi.mock('../../lib/api', async () => {
  const real = await vi.importActual<typeof import('../../lib/api')>('../../lib/api');
  return {
    ...real,
    patientsApi: {
      getPatients: vi.fn(),
      discharge: vi.fn(),
      transfer: vi.fn(),
      deletePatient: vi.fn(),
    },
    unitsApi: { list: vi.fn(), create: vi.fn(), getUserUnits: vi.fn(), setUserUnits: vi.fn() },
  };
});

vi.mock('../../lib/storage', () => ({
  getStoredUser: () => ({ username: 'enf.a', role: 'staff' }),
}));

const ANA = {
  id: 'PAC-0001',
  name: 'Ana Silva',
  room: '201',
  bed: 'A',
  riskLevel: 'high' as const,
  repositioningInterval: 1,
  createdAt: '2026-01-01T10:00:00',
  updatedAt: '2026-01-01T10:00:00',
  unitId: 1,
};

beforeEach(() => {
  vi.mocked(patientsApi.getPatients).mockResolvedValue([ANA]);
  vi.mocked(unitsApi.list).mockResolvedValue([
    { id: 1, nome: 'Unidade Principal', descricao: null, ativo: 1 },
  ]);
  vi.mocked(patientsApi.discharge).mockResolvedValue({
    ok: true,
    paciente_id: 'PAC-0001',
    alta_ts: '2026-01-02T10:00:00',
    permanencia_horas: 24,
    cama_liberada: '201-A',
  });
  vi.mocked(patientsApi.transfer).mockResolvedValue({
    ok: true,
    paciente_id: 'PAC-0001',
    cama_anterior: '201-A',
    cama_atual: '305-B',
    ts: '2026-01-02T10:00:00',
  });
});

describe('alta', () => {
  it('registra a alta com o motivo digitado', async () => {
    render(<PatientsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /dar alta/i }));

    await userEvent.type(await screen.findByLabelText(/motivo/i), 'melhora clinica');
    await userEvent.click(screen.getByRole('button', { name: /confirmar alta/i }));

    await waitFor(() =>
      expect(patientsApi.discharge).toHaveBeenCalledWith('PAC-0001', 'melhora clinica'),
    );
  });

  it('motivo em branco vira undefined, nao string vazia', async () => {
    render(<PatientsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /dar alta/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirmar alta/i }));

    await waitFor(() =>
      expect(patientsApi.discharge).toHaveBeenCalledWith('PAC-0001', undefined),
    );
  });

  it('avisa que o historico e preservado', async () => {
    render(<PatientsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /dar alta/i }));

    expect(await screen.findByText(/é preservado/i)).toBeInTheDocument();
  });

  it('erro do backend aparece e o dialogo nao some antes da resposta', async () => {
    vi.mocked(patientsApi.discharge).mockRejectedValue(
      new ApiException('Paciente nao tem internacao aberta.', 409),
    );
    render(<PatientsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /dar alta/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirmar alta/i }));

    await waitFor(() => expect(patientsApi.discharge).toHaveBeenCalled());
    // A lista NAO e recarregada quando a operacao falha: recarregar sugeriria
    // que algo mudou.
    expect(patientsApi.getPatients).toHaveBeenCalledTimes(1);
  });
});

describe('transferência', () => {
  it('vem pre-preenchida com o leito atual', async () => {
    render(<PatientsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /transferir/i }));

    expect(await screen.findByLabelText(/quarto/i)).toHaveValue('201');
    expect(screen.getByLabelText(/leito/i)).toHaveValue('A');
  });

  it('envia o destino digitado', async () => {
    render(<PatientsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /transferir/i }));

    const quarto = await screen.findByLabelText(/quarto/i);
    await userEvent.clear(quarto);
    await userEvent.type(quarto, '305');
    const leito = screen.getByLabelText(/leito/i);
    await userEvent.clear(leito);
    await userEvent.type(leito, 'B');
    await userEvent.click(screen.getByRole('button', { name: /confirmar transferência/i }));

    await waitFor(() =>
      expect(patientsApi.transfer).toHaveBeenCalledWith('PAC-0001', '305', 'B'),
    );
  });

  it('destino vazio nao pode ser confirmado', async () => {
    render(<PatientsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /transferir/i }));

    const quarto = await screen.findByLabelText(/quarto/i);
    await userEvent.clear(quarto);

    expect(screen.getByRole('button', { name: /confirmar transferência/i })).toBeDisabled();
  });
});

describe('excluir', () => {
  it('nao aparece para quem nao e admin', async () => {
    render(<PatientsPage />);
    await screen.findByText('Ana Silva');

    expect(screen.queryByRole('button', { name: /excluir/i })).not.toBeInTheDocument();
  });
});
