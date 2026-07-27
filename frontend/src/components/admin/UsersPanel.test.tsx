/**
 * Painel de usuários — a tela que faltava para as cinco rotas `/api/usuarios*`.
 *
 * O foco dos testes é o que a tela promete ao operador: que a ação de fato
 * chamou o backend, e que as regras que o backend impõe (não desativar a
 * própria conta, não ficar sem admin) cheguem ao usuário em vez de virarem um
 * erro genérico.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UsersPanel } from './UsersPanel';
import { ApiException } from '../../lib/api';
import type { Usuario } from '../../lib/api';

vi.mock('../../lib/api', async (importarOriginal) => {
  const original = await importarOriginal<typeof import('../../lib/api')>();
  return {
    ...original,
    usuariosApi: {
      listar: vi.fn(),
      criar: vi.fn(),
      alterarPapel: vi.fn(),
      alterarAtivo: vi.fn(),
      definirSenha: vi.fn(),
      trocarPropriaSenha: vi.fn(),
    },
  };
});

vi.mock('../../lib/storage', () => ({
  getStoredUser: () => ({ username: 'ana', role: 'admin' }),
}));

import { usuariosApi } from '../../lib/api';

const usuario = (over: Partial<Usuario> = {}): Usuario => ({
  username: 'bruno',
  display_name: 'Bruno Souza',
  role: 'staff',
  ativo: true,
  created_at: '2026-01-01T10:00:00',
  ...over,
});

beforeEach(() => {
  vi.mocked(usuariosApi.listar).mockResolvedValue([
    usuario({ username: 'ana', role: 'admin' }),
    usuario(),
  ]);
  vi.mocked(usuariosApi.alterarPapel).mockResolvedValue({
    ok: true,
    username: 'bruno',
    role: 'admin',
  });
  vi.mocked(usuariosApi.alterarAtivo).mockResolvedValue({
    ok: true,
    username: 'bruno',
    ativo: false,
  });
  vi.mocked(usuariosApi.definirSenha).mockResolvedValue({ ok: true, username: 'bruno' });
  vi.mocked(usuariosApi.criar).mockResolvedValue({ username: 'novo', role: 'staff' });
});

const linhaDe = async (nome: string) => {
  const alvo = await screen.findByText(nome);
  return alvo.closest('div[data-slot="card"]') ?? alvo.parentElement!.parentElement!;
};

describe('listagem', () => {
  it('mostra papel e estado de cada conta', async () => {
    render(<UsersPanel />);

    expect(await screen.findByText('bruno')).toBeInTheDocument();
    expect(screen.getByText('Administrador')).toBeInTheDocument();
    expect(screen.getByText('Equipe')).toBeInTheDocument();
  });

  it('marca a própria conta', async () => {
    render(<UsersPanel />);
    expect(await screen.findByText('você')).toBeInTheDocument();
  });
});

describe('ações', () => {
  it('promove a admin', async () => {
    render(<UsersPanel />);
    const linha = await linhaDe('bruno');

    await userEvent.click(within(linha as HTMLElement).getByRole('button', { name: /tornar admin/i }));

    await waitFor(() => {
      expect(usuariosApi.alterarPapel).toHaveBeenCalledWith('bruno', 'admin');
    });
  });

  it('desativar exige confirmação', async () => {
    render(<UsersPanel />);
    const linha = await linhaDe('bruno');

    await userEvent.click(within(linha as HTMLElement).getByRole('button', { name: /desativar/i }));

    // Desativar encerra o acesso de alguém no meio de um plantão; um clique
    // acidental não pode bastar.
    expect(usuariosApi.alterarAtivo).not.toHaveBeenCalled();
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
  });

  it('não oferece desativar a própria conta', async () => {
    // O backend responde 409 `autodesativacao`; oferecer o botão seria propor
    // uma ação que sempre falha.
    render(<UsersPanel />);
    const linha = await linhaDe('ana');

    expect(within(linha as HTMLElement).getByRole('button', { name: /desativar/i })).toBeDisabled();
  });

  it('mostra a mensagem do backend quando a regra recusa', async () => {
    // "Nao e possivel rebaixar o ultimo administrador ativo" explica a regra
    // melhor do que qualquer texto genérico da tela.
    vi.mocked(usuariosApi.alterarPapel).mockRejectedValue(
      new ApiException('Nao e possivel rebaixar o ultimo administrador ativo.', 409)
    );
    const { toast } = await import('sonner');
    const erro = vi.spyOn(toast, 'error');

    render(<UsersPanel />);
    const linha = await linhaDe('ana');
    await userEvent.click(
      within(linha as HTMLElement).getByRole('button', { name: /tornar equipe/i })
    );

    await waitFor(() => {
      expect(erro).toHaveBeenCalledWith('Nao e possivel rebaixar o ultimo administrador ativo.');
    });
  });
});

describe('reset de senha', () => {
  it('recusa senha curta antes de chamar o backend', async () => {
    render(<UsersPanel />);
    const linha = await linhaDe('bruno');
    await userEvent.click(
      within(linha as HTMLElement).getByRole('button', { name: /redefinir senha/i })
    );

    const dialogo = await screen.findByRole('alertdialog');
    await userEvent.type(within(dialogo).getByLabelText(/nova senha/i), 'curta');

    expect(within(dialogo).getByRole('button', { name: /^redefinir$/i })).toBeDisabled();
    expect(usuariosApi.definirSenha).not.toHaveBeenCalled();
  });

  it('envia a nova senha quando válida', async () => {
    render(<UsersPanel />);
    const linha = await linhaDe('bruno');
    await userEvent.click(
      within(linha as HTMLElement).getByRole('button', { name: /redefinir senha/i })
    );

    const dialogo = await screen.findByRole('alertdialog');
    await userEvent.type(within(dialogo).getByLabelText(/nova senha/i), 'senha-longa-o-bastante');
    await userEvent.click(within(dialogo).getByRole('button', { name: /^redefinir$/i }));

    await waitFor(() => {
      expect(usuariosApi.definirSenha).toHaveBeenCalledWith('bruno', 'senha-longa-o-bastante');
    });
  });
});

describe('criacao de conta', () => {
  it('cria o usuario a partir do painel', async () => {
    // O cadastro anônimo fecha assim que existe o primeiro usuário, e a tela de
    // cadastro só aparece deslogado: sem este caminho, criar o segundo usuário
    // da instalação só era possível por `curl`.
    render(<UsersPanel />);
    await screen.findByText('bruno');

    await userEvent.click(screen.getByRole('button', { name: /criar usuário/i }));
    const dialogo = await screen.findByRole('alertdialog');
    await userEvent.type(within(dialogo).getByLabelText(/^usuário$/i), 'carla');
    await userEvent.type(within(dialogo).getByLabelText(/senha/i), 'senha-longa-o-bastante');
    await userEvent.click(within(dialogo).getByRole('button', { name: /^criar$/i }));

    await waitFor(() => {
      expect(usuariosApi.criar).toHaveBeenCalledWith('carla', 'senha-longa-o-bastante', undefined);
    });
  });

  it('recusa senha abaixo da politica antes de chamar o backend', async () => {
    render(<UsersPanel />);
    await screen.findByText('bruno');

    await userEvent.click(screen.getByRole('button', { name: /criar usuário/i }));
    const dialogo = await screen.findByRole('alertdialog');
    await userEvent.type(within(dialogo).getByLabelText(/^usuário$/i), 'carla');
    await userEvent.type(within(dialogo).getByLabelText(/senha/i), 'curta');

    expect(within(dialogo).getByRole('button', { name: /^criar$/i })).toBeDisabled();
    expect(usuariosApi.criar).not.toHaveBeenCalled();
  });
});
