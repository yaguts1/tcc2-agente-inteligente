/**
 * Tabela de alertas — onde o clique de fato acontece.
 *
 * O AlertsContext ja e testado, mas ele so expoe as funcoes; quem chama, mostra
 * confirmacao e controla o estado de "processando" e este componente. Uma falha
 * aqui deixa a acao inacessivel mesmo com o backend perfeito.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AlertsTable } from './AlertsTable';
import type { Alert, BatchResult } from '../../lib/api';

const AGORA = new Date('2026-01-01T12:00:00Z');

function alerta(over: Partial<Alert> = {}): Alert {
  return {
    id: 'PAC-0001__2026-01-01T10:00:00',
    patientName: 'Maria Silva',
    room: '101',
    bed: 'A',
    lastRepositioning: '2026-01-01T08:00:00Z',
    // No futuro: nao atrasado.
    nextRepositioning: '2026-01-01T14:00:00Z',
    riskLevel: 'high',
    status: 'pending',
    closureOrigin: null,
    closedBy: null,
    ...over,
  };
}

const loteOk = (ids: string[]): BatchResult => ({
  ok: true,
  processed: ids.length,
  failed: 0,
  errors: [],
});

function renderizar(props: Partial<Parameters<typeof AlertsTable>[0]> = {}) {
  const onAcknowledge = vi.fn().mockResolvedValue(undefined);
  const onComplete = vi.fn().mockResolvedValue(undefined);
  const onBulkAcknowledge = vi.fn(async (ids: string[]) => loteOk(ids));
  const onBulkComplete = vi.fn(async (ids: string[]) => loteOk(ids));
  const utils = render(
    <AlertsTable
      alerts={[alerta()]}
      onAcknowledge={onAcknowledge}
      onComplete={onComplete}
      onBulkAcknowledge={onBulkAcknowledge}
      onBulkComplete={onBulkComplete}
      isLoading={false}
      {...props}
    />,
  );
  return { ...utils, onAcknowledge, onComplete, onBulkAcknowledge, onBulkComplete };
}

describe('acoes individuais', () => {
  it('reconhece o alerta ao clicar', async () => {
    const { onAcknowledge } = renderizar();

    const linha = screen.getByRole('row', { name: /Maria Silva/i });
    await userEvent.click(within(linha).getByRole('button', { name: /reconhecer/i }));

    expect(onAcknowledge).toHaveBeenCalledWith('PAC-0001__2026-01-01T10:00:00');
  });

  it('exige confirmacao antes de concluir', async () => {
    const { onComplete } = renderizar();

    await userEvent.click(screen.getByRole('button', { name: /reposicionar/i }));

    // Concluir registra que o paciente FOI reposicionado. Disparar direto no
    // clique tornaria um toque acidental indistinguivel de um cuidado
    // prestado, e o registro clinico ficaria falso.
    expect(onComplete).not.toHaveBeenCalled();
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
  });

  it('conclui apos confirmar no dialogo', async () => {
    const { onComplete } = renderizar();

    await userEvent.click(screen.getByRole('button', { name: /reposicionar/i }));
    const dialogo = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialogo).getByRole('button', { name: /confirmar|sim/i }));

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith('PAC-0001__2026-01-01T10:00:00');
    });
  });

  it('nao conclui se o usuario cancelar', async () => {
    const { onComplete } = renderizar();

    await userEvent.click(screen.getByRole('button', { name: /reposicionar/i }));
    const dialogo = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialogo).getByRole('button', { name: /cancelar/i }));

    expect(onComplete).not.toHaveBeenCalled();
  });
});

describe('falha na acao', () => {
  it('nao deixa o botao travado quando reconhecer falha', async () => {
    // O AlertsContext RE-LANCA o erro apos avisar o usuario. Se o handler nao
    // limpar o estado de "processando" num finally, a linha fica travada: o
    // botao permanece desabilitado e a enfermeira nao consegue tentar de novo
    // sem recarregar a pagina.
    const onAcknowledge = vi.fn().mockRejectedValue(new Error('falhou'));
    renderizar({ onAcknowledge });

    const linha = screen.getByRole('row', { name: /Maria Silva/i });
    await userEvent.click(within(linha).getByRole('button', { name: /reconhecer/i }));

    await waitFor(() => {
      expect(within(linha).getByRole('button', { name: /reconhecer/i })).toBeEnabled();
    });
  });

  it('nao deixa o dialogo preso quando concluir falha', async () => {
    const onComplete = vi.fn().mockRejectedValue(new Error('falhou'));
    renderizar({ onComplete });

    await userEvent.click(screen.getByRole('button', { name: /reposicionar/i }));
    const dialogo = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialogo).getByRole('button', { name: /confirmar|sim/i }));

    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
  });
});

describe('alerta atrasado', () => {
  it('indica o atraso de forma acessivel, e nao so por cor', async () => {
    vi.setSystemTime(AGORA);
    renderizar({
      alerts: [alerta({ nextRepositioning: '2026-01-01T09:00:00Z' })], // 3h no passado
    });

    // Cor de fundo e icone sem rotulo nao chegam a quem usa leitor de tela nem
    // a quem nao distingue as cores — e "atrasado" e justamente a informacao
    // que decide a prioridade do atendimento.
    const linha = screen.getByRole('row', { name: /Maria Silva/i });
    expect(within(linha).getByText(/atrasad/i)).toBeInTheDocument();

    vi.useRealTimers();
  });
});

describe('acoes em lote', () => {
  const doisAlertas = () => [
    alerta({ id: 'PAC-0001__a', patientName: 'Maria Silva' }),
    alerta({ id: 'PAC-0002__b', patientName: 'Joao Souza' }),
  ];

  async function selecionarTodosEReconhecer() {
    await userEvent.click(screen.getByLabelText('Selecionar todos os alertas'));
    // A barra de lote aparece com os itens selecionados; o botao dela e o
    // ultimo "Reconhecer" do documento (as linhas tambem tem o seu).
    const botoes = await screen.findAllByRole('button', { name: /reconhecer/i });
    await userEvent.click(botoes[botoes.length - 1]);
  }

  it('manda UMA requisicao de lote, nao uma por alerta', async () => {
    // Este teste afirmava `onAcknowledge` chamado 2x — ou seja, sacramentava o
    // `Promise.all(ids.map(...))` que era o defeito. N requisicoes soltas nao
    // tem como reportar sucesso parcial: `Promise.all` rejeita no primeiro
    // erro e o resto do lote fica invisivel.
    const { onBulkAcknowledge, onAcknowledge } = renderizar({ alerts: doisAlertas() });

    await selecionarTodosEReconhecer();

    await waitFor(() => {
      expect(onBulkAcknowledge).toHaveBeenCalledTimes(1);
    });
    expect(onBulkAcknowledge).toHaveBeenCalledWith(['PAC-0001__a', 'PAC-0002__b']);
    expect(onAcknowledge).not.toHaveBeenCalled();
  });

  it('limpa a selecao quando o lote inteiro passa', async () => {
    renderizar({ alerts: doisAlertas() });

    await selecionarTodosEReconhecer();

    await waitFor(() => {
      expect(screen.queryByText(/selecionado/i)).not.toBeInTheDocument();
    });
  });

  it('mantem selecionados apenas os que falharam', async () => {
    // O caso que o `Promise.all` tornava impossivel de tratar: parte do lote
    // grava e parte nao (409 quando outra pessoa ja agiu sobre o alerta).
    // Limpar tudo esconderia quais precisam de nova tentativa; manter tudo
    // faria o proximo clique reprocessar o que ja deu certo.
    const onBulkAcknowledge = vi.fn(async (): Promise<BatchResult> => ({
      ok: false,
      processed: 1,
      failed: 1,
      errors: [{ alert_id: 'PAC-0002__b', error: 'transicao_invalida' }],
    }));
    renderizar({ alerts: doisAlertas(), onBulkAcknowledge });

    await selecionarTodosEReconhecer();

    await waitFor(() => {
      expect(screen.getByText(/1 selecionado/i)).toBeInTheDocument();
    });

    // E o que sobrou selecionado e exatamente o que falhou.
    const linhaQueFalhou = screen.getByRole('row', { name: /Joao Souza/i });
    expect(within(linhaQueFalhou).getByRole('checkbox')).toBeChecked();
    const linhaQuePassou = screen.getByRole('row', { name: /Maria Silva/i });
    expect(within(linhaQuePassou).getByRole('checkbox')).not.toBeChecked();
  });
});
