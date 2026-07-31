/**
 * A tela de alertas é usável no aparelho que fica à beira do leito.
 *
 * A suíte inteira roda com `matchMedia` devolvendo `matches: false`
 * (`setupTests.ts`), ou seja, sempre no layout de tabela. Sem este arquivo, a
 * camada de cartões — que é a que a enfermagem de fato usa — não seria
 * exercitada por teste nenhum, e quebraria em silêncio.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { CartaoDeAlerta } from './CartaoDeAlerta';

// Anotado, e nao inferido: `typeof` de um literal com `room: '201'` da
// `string`, e `Partial` disso vira `string | undefined` — o teste de leito
// ausente nao compilaria, embora `room`/`bed` sejam anulaveis no contrato
// desde 2.1. O tipo aqui e o do componente, nao o do literal.
const ALERTA: React.ComponentProps<typeof CartaoDeAlerta>['alerta'] = {
  id: 'PAC-0001__2026-06-01T08:00:00',
  patientName: 'Maria Silva',
  room: '201',
  bed: 'A',
  riskLevel: 'high',
  status: 'pending',
  lastRepositioning: '2026-06-01T07:00:00',
  nextRepositioning: '2026-06-01T08:00:00',
  site: 'trocanter_direito',
  minutesOpen: 0,
  escalationLevel: 'normal',
};

function montar(sobrescreve: Partial<typeof ALERTA> = {}, props = {}) {
  return render(
    <CartaoDeAlerta
      alerta={{ ...ALERTA, ...sobrescreve }}
      atrasado={false}
      selecionado={false}
      processando={false}
      rotuloDeSitio={(s) => (s === 'trocanter_direito' ? 'Trocânter D' : null)}
      selo={{ risco: <span>Alto</span>, status: <span>Pendente</span> }}
      tempo={{ proximo: '08:00', restante: 'agora', ultimo: '07:00' }}
      onSelecionar={vi.fn()}
      onReconhecer={vi.fn()}
      onReposicionar={vi.fn()}
      {...props}
    />,
  );
}

describe('CartaoDeAlerta', () => {
  it('os botões alcançam o alvo de toque de 44px', () => {
    montar();

    // `size="sm"` (32px) era o que a tabela usava, e a enfermagem opera a tela
    // DE LUVA. Errar o alvo não é um clique perdido: ou marca o paciente
    // errado, ou faz desistir da tela e registrar no papel.
    //
    // O teste olha a CLASSE e não a altura computada: jsdom não faz layout, e
    // um teste que medisse `getBoundingClientRect` passaria sempre com zero.
    for (const nome of [/reconhecer/i, /reposicionar/i]) {
      const botao = screen.getByRole('button', { name: nome });
      expect(botao.className).toContain('min-h-11');
    }
  });

  it('o leito vem em destaque, antes do nome', () => {
    const { container } = montar();

    // Numa ala de 30 leitos, quem está com o aparelho na mão está indo ATÉ um
    // quarto: o leito é o que se procura, o nome é o que confirma. Na tabela a
    // ordem é a inversa, e é a ordem certa lá — a tabela é lida sentado.
    const texto = container.textContent ?? '';
    expect(texto.indexOf('201 / A')).toBeLessThan(texto.indexOf('Maria Silva'));
    expect(texto).toContain('201 / A');
  });

  it('mostra o sítio anatômico', () => {
    montar();
    // "Vire o paciente" interrompe sem orientar. "Trocânter D" diz para qual
    // lado virar.
    expect(screen.getByText('Trocânter D')).toBeInTheDocument();
  });

  it('leito ausente não vira "null / null"', () => {
    montar({ room: null, bed: null });
    // `room`/`bed` são anuláveis no contrato (2.1) — paciente sem leito
    // atribuído existe.
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('a caixa de seleção tem área de toque própria', () => {
    montar();
    const caixa = screen.getByRole('checkbox', { name: /selecionar maria/i });
    const rotulo = caixa.closest('label');
    // O controle desenhado tem 16px. Acertá-lo de luva, ao lado de um botão de
    // ação, é como marcar o paciente errado por um milímetro.
    expect(rotulo?.className).toContain('p-2');
  });

  it('não oferece reconhecer o que já está reconhecido', () => {
    montar({ status: 'acknowledged' });
    expect(screen.getByRole('button', { name: /reconhecer/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /reposicionar/i })).toBeEnabled();
  });

  it('durante o processamento, nenhuma das duas ações aceita clique', () => {
    montar({}, { processando: true });
    // Sem isto, dois toques rápidos — comuns quando a tela demora e a pessoa
    // insiste — viram duas requisições para o mesmo alerta.
    expect(screen.getByRole('button', { name: /reconhecer/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /reposicionar/i })).toBeDisabled();
  });

  it('atrasado é sinalizado por ícone, e não só por cor', () => {
    const { container } = montar({}, { atrasado: true });
    // Cor sozinha é inacessível, e a tela é usada por quem pode ter daltonismo
    // sob iluminação ruim de madrugada.
    expect(within(container).getByText('08:00 · agora').className).toContain(
      'text-danger',
    );
    expect(container.querySelector('svg.text-danger')).toBeTruthy();
  });
});

describe('a troca de layout', () => {
  it('em tela estreita a AlertsTable rende cartões, e não a tabela', async () => {
    // A suíte inteira roda com `matches: false`. Este é o único ponto que
    // exercita o outro ramo — e a troca é o que quebraria em silêncio num
    // refactor, porque o layout de tabela continuaria passando em tudo.
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );

    const { AlertsTable } = await import('./AlertsTable');
    const { container } = render(
      <AlertsTable
        alerts={[ALERTA as never]}
        onAcknowledge={vi.fn()}
        onComplete={vi.fn()}
        onBulkAcknowledge={vi.fn().mockResolvedValue({ processed: 0, failed: 0, errors: [] })}
        onBulkComplete={vi.fn().mockResolvedValue({ processed: 0, failed: 0, errors: [] })}
        isLoading={false}
      />,
    );

    expect(container.querySelector('table')).toBeNull();
    // Uma arvore SO: cada alerta aparece uma vez, e nao duas. Duplicar faria o
    // leitor de tela anunciar o mesmo paciente duas vezes, com dois botoes
    // "Reposicionar" para ele.
    expect(screen.getAllByRole('button', { name: /reposicionar/i })).toHaveLength(1);

    vi.unstubAllGlobals();
  });
});
