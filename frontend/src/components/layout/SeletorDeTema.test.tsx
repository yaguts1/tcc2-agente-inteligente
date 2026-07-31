/**
 * O modo escuro está ligado, e continua ligado.
 *
 * Os tokens `.dark` existiam em `globals.css` desde sempre e nada aplicava a
 * classe — o único `useTheme` do projeto vivia dentro de `ui/sonner.tsx`,
 * conectado a provider nenhum. Uma ala às 03:00 recebia tela branca no talo,
 * num quarto escuro, com o paciente dormindo.
 *
 * Dois testes, e o segundo é o que envelhece melhor: enquanto houver componente
 * com cor neutra fixa (`bg-white`, `text-gray-600`), o tema pode estar
 * perfeitamente ligado e a tela ainda assim quebrar em pedaços — e o sintoma
 * seria texto cinza-claro sobre fundo escuro no popover de alertas críticos,
 * que é precisamente a tela usada de madrugada.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ThemeProvider } from 'next-themes';
import { SeletorDeTema } from './SeletorDeTema';

describe('SeletorDeTema', () => {
  it('aplica a classe que a folha de estilo espera', async () => {
    render(
      <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
        <SeletorDeTema />
      </ThemeProvider>,
    );

    // `globals.css` usa `@custom-variant dark (&:is(.dark *))`: sem a classe
    // `dark` no elemento raiz, o bloco inteiro de tokens fica inerte.
    screen.getByRole('radio', { name: 'Escuro' }).click();

    await waitFor(() =>
      expect(document.documentElement.classList.contains('dark')).toBe(true),
    );
  });

  it('oferece o estado "Sistema", e não só claro/escuro', () => {
    render(
      <ThemeProvider attribute="class" defaultTheme="system">
        <SeletorDeTema />
      </ThemeProvider>,
    );
    // O tablet da ala noturna já está em escuro no SO e resolve sozinho; a
    // estação compartilhada frequentemente não está, e quem entra no plantão
    // da noite precisa poder forçar. Os dois casos existem.
    expect(screen.getByRole('radio', { name: 'Sistema' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Claro' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Escuro' })).toBeInTheDocument();
  });
});

describe('cores fixas', () => {
  /**
   * Neutros fixos ignoram o tema. `text-gray-600` sobre fundo escuro fica
   * ilegível, e `bg-white` cria um retângulo branco no meio de uma tela escura.
   *
   * `text-white` sobre botão colorido (`bg-destructive`, `bg-blue-600`) NÃO
   * entra na lista: ali o contraste é com a cor do próprio botão, que é a mesma
   * nos dois temas. Idem `bg-black/50`, que é véu de modal.
   */
  const PROIBIDAS =
    /\b(?:bg|text|border)-(?:white|black|gray-\d{2,3}|slate-\d{2,3}|zinc-\d{2,3})\b/g;

  function arquivosTsx(dir: string): string[] {
    return readdirSync(dir).flatMap((nome) => {
      const caminho = join(dir, nome);
      if (statSync(caminho).isDirectory()) return arquivosTsx(caminho);
      // O proprio arquivo de teste cita as classes proibidas — no comentario
      // que explica as excecoes e na regex. Varrer testes faria o guarda se
      // auto-detectar, e a correcao natural (afrouxar a regex) o deixaria
      // cego para o caso real.
      if (caminho.endsWith('.test.tsx')) return [];
      return caminho.endsWith('.tsx') ? [caminho] : [];
    });
  }

  it('nenhum componente hardcoda cor neutra', () => {
    const achados: string[] = [];

    for (const arquivo of arquivosTsx(join(__dirname, '..', '..'))) {
      const conteudo = readFileSync(arquivo, 'utf-8');
      for (const linha of conteudo.split('\n')) {
        for (const classe of linha.match(PROIBIDAS) ?? []) {
          // Exceções justificadas acima.
          if (classe === 'text-white' || classe === 'bg-black') continue;
          achados.push(`${arquivo.split('src')[1]}: ${classe}`);
        }
      }
    }

    expect(achados, achados.join('\n')).toEqual([]);
  });

  /**
   * Tom claro (50/100) de uma cor COM significado — azul de selecionado,
   * vermelho de perigo, verde de sucesso — é uma superfície quase branca. Ela
   * não é "neutra", então escapou da regra acima, e continuava quase branca no
   * tema escuro: uma linha selecionada virava uma faixa clara atravessando uma
   * tela escura.
   *
   * Foi uma lacuna real da primeira versão deste guarda: o modo escuro foi
   * ligado e oito ocorrências seguiram erradas, sem nada acusar. A regra não
   * pede que a cor suma — ela carrega informação — e sim que exista o par
   * escuro, que preserva o significado e inverte a luminosidade.
   */
  const TOM_CLARO =
    /\b(?:bg|text|border)-(?:blue|red|green|yellow|amber|indigo|purple)-(?:50|100)\b/g;

  it('todo tom claro tem par escuro', () => {
    const achados: string[] = [];

    for (const arquivo of arquivosTsx(join(__dirname, '..', '..'))) {
      const conteudo = readFileSync(arquivo, 'utf-8');
      for (const classe of conteudo.match(TOM_CLARO) ?? []) {
        const [prop, familia, tom] = classe.split('-');
        const par = `dark:${prop}-${familia}-${tom === '50' ? '950' : '900'}`;
        if (!conteudo.includes(par)) {
          achados.push(`${arquivo.split('src')[1]}: ${classe} sem ${par}`);
        }
      }
    }

    expect(achados, achados.join('\n')).toEqual([]);
  });
});
