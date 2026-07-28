/**
 * Unidades: a tela precisa deixar visível a diferença entre "vê tudo" e
 * "não vê nada".
 *
 * As duas situações são visualmente parecidas — nenhuma caixa marcada — e
 * clinicamente opostas. Admin ignora a lista e enxerga todas as alas; um staff
 * com lista vazia não enxerga paciente nenhum. Se a tela mostrar as duas do
 * mesmo jeito, quem administra acredita ter dado acesso e não deu, ou acredita
 * ter restringido um admin e não restringiu.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UnitsPanel } from './UnitsPanel';
import { unitsApi, usuariosApi } from '../../lib/api';

vi.mock('../../lib/api', async () => {
  const real = await vi.importActual<typeof import('../../lib/api')>('../../lib/api');
  return {
    ...real,
    unitsApi: {
      list: vi.fn(),
      create: vi.fn(),
      getUserUnits: vi.fn(),
      setUserUnits: vi.fn(),
    },
    usuariosApi: { ...real.usuariosApi, listar: vi.fn() },
  };
});

const UNIDADES = [
  { id: 1, nome: 'Unidade Principal', descricao: null, ativo: 1 },
  { id: 2, nome: 'Ala Sul', descricao: null, ativo: 1 },
];

beforeEach(() => {
  vi.mocked(unitsApi.list).mockResolvedValue(UNIDADES);
  vi.mocked(usuariosApi.listar).mockResolvedValue([
    { username: 'chefe', display_name: 'Chefe', role: 'admin', ativo: true, created_at: '' },
    { username: 'enf.a', display_name: 'Enf A', role: 'staff', ativo: true, created_at: '' },
    { username: 'novato', display_name: 'Novato', role: 'staff', ativo: true, created_at: '' },
  ] as never);
  vi.mocked(unitsApi.getUserUnits).mockImplementation(async (username: string) => ({
    username,
    unidades: username === 'enf.a' ? [1] : [],
  }));
  vi.mocked(unitsApi.setUserUnits).mockResolvedValue({
    ok: true,
    username: 'enf.a',
    unidades: [],
  });
});

const blocoDe = async (username: string): Promise<HTMLElement> => {
  const alvo = await screen.findByText(username);
  // `closest` devolve `Element`; `within` exige `HTMLElement`. O cast é seguro
  // aqui porque o seletor casa com uma `div` do próprio componente.
  return (alvo.closest('div.border-b') as HTMLElement | null)
    ?? (alvo.parentElement!.parentElement as HTMLElement);
};

describe('unidades', () => {
  it('lista as unidades existentes', async () => {
    render(<UnitsPanel />);

    // Cada nome aparece mais de uma vez de propósito: como badge na lista de
    // unidades e como rótulo da caixa de cada usuário.
    expect((await screen.findAllByText('Ala Sul')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Unidade Principal').length).toBeGreaterThan(0);
  });
});

describe('quem enxerga o que', () => {
  it('admin aparece como "todas por papel", sem caixas marcadas', async () => {
    render(<UnitsPanel />);

    const bloco = await blocoDe('chefe');
    expect(within(bloco).getByText(/enxerga todas as unidades, por papel/i)).toBeInTheDocument();
    expect(within(bloco).queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('staff sem unidade recebe aviso de que nao ve nada', async () => {
    render(<UnitsPanel />);

    const bloco = await blocoDe('novato');
    expect(
      within(bloco).getByText(/não vê paciente nem alerta nenhum/i),
    ).toBeInTheDocument();
  });

  it('staff com unidade nao recebe o aviso', async () => {
    render(<UnitsPanel />);

    const bloco = await blocoDe('enf.a');
    await waitFor(() =>
      expect(
        within(bloco).queryByText(/não vê paciente nem alerta nenhum/i),
      ).not.toBeInTheDocument(),
    );
  });

  it('desmarcar a ultima unidade salva lista vazia', async () => {
    render(<UnitsPanel />);
    const bloco = await blocoDe('enf.a');

    const caixas = within(bloco).getAllByRole('checkbox');
    await userEvent.click(caixas[0]);

    await waitFor(() =>
      expect(unitsApi.setUserUnits).toHaveBeenCalledWith('enf.a', []),
    );
  });
});
