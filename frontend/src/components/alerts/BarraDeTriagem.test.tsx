/**
 * O interruptor entre "meu trabalho" e "a ala".
 *
 * O caso que mais importa é o de ZERO leitos assumidos. Um interruptor que
 * filtra para vazio é pior que ausente: quem o liga vê a lista vazia e conclui
 * que o sistema está quebrado, não que ainda não assumiu leito nenhum — e a
 * conclusão "está quebrado" contamina a confiança no painel inteiro, inclusive
 * nos alertas.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BarraDeTriagem } from './BarraDeTriagem';

function montar(props: Partial<React.ComponentProps<typeof BarraDeTriagem>> = {}) {
  return render(
    <BarraDeTriagem
      soMeus={false}
      quantidade={3}
      onAlternar={vi.fn()}
      onLiberarTodos={vi.fn()}
      {...props}
    />,
  );
}

describe('BarraDeTriagem', () => {
  it('some quando não há leito assumido', () => {
    const { container } = montar({ quantidade: 0, soMeus: false });
    expect(container).toBeEmptyDOMElement();
  });

  it('mas NÃO some se o filtro está ligado', () => {
    // Caso real: a pessoa ligou o filtro e depois liberou o último leito. Se a
    // barra sumisse aqui, o filtro ficaria ligado sem controle para desligá-lo
    // — a lista vazia, e nada na tela explicando por quê.
    montar({ quantidade: 0, soMeus: true });
    expect(screen.getByRole('button', { name: /meus leitos/i })).toBeInTheDocument();
  });

  it('mostra quantos leitos são meus', () => {
    montar({ quantidade: 5 });
    expect(screen.getByRole('button', { name: /5/ })).toBeInTheDocument();
  });

  it('o estado do filtro é anunciável, não só visível', () => {
    // `aria-pressed` porque o único sinal de "ligado" é a variante do botão,
    // que é cor — inacessível sozinha.
    montar({ soMeus: true });
    expect(screen.getByRole('button', { name: /meus leitos/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('alterna ao clicar', async () => {
    const onAlternar = vi.fn();
    montar({ onAlternar });

    await userEvent.click(screen.getByRole('button', { name: /ver só os meus/i }));

    expect(onAlternar).toHaveBeenCalledTimes(1);
  });

  it('oferece encerrar o plantão quando há leitos', async () => {
    // Sem este botão ninguém libera leito a leito, e as atribuições ficariam
    // vivas indefinidamente até "meus pacientes" acumular o hospital inteiro.
    const onLiberarTodos = vi.fn();
    montar({ quantidade: 2, onLiberarTodos });

    await userEvent.click(screen.getByRole('button', { name: /encerrar plantão/i }));

    expect(onLiberarTodos).toHaveBeenCalled();
  });

  it('não oferece encerrar plantão sem leitos', () => {
    montar({ quantidade: 0, soMeus: true });
    expect(screen.queryByRole('button', { name: /encerrar plantão/i })).toBeNull();
  });

  it('o alvo de toque do interruptor é de beira de leito', () => {
    montar();
    expect(
      screen.getByRole('button', { name: /ver só os meus/i }).className,
    ).toContain('min-h-11');
  });
});
