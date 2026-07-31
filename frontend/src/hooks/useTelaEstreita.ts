import { useEffect, useState } from 'react';

/**
 * Verdadeiro abaixo do breakpoint `lg` do Tailwind (1024px).
 *
 * A tela de alertas troca de TABELA para CARTÕES nesse ponto, e a troca é feita
 * em JavaScript — renderizando uma árvore só — em vez do caminho mais óbvio, que
 * seria montar as duas e esconder uma com `lg:hidden` / `hidden lg:block`.
 *
 * A razão não é desempenho, embora o DOM dobrado também custe: é que as duas
 * árvores ficam AMBAS no documento. Um leitor de tela ignora `display: none`
 * para layout mas o conteúdo escondido por CSS continua no acessibilidade tree
 * em várias combinações de navegador e leitor — e o resultado é cada alerta
 * sendo anunciado DUAS VEZES, com dois botões "Reposicionar" para o mesmo
 * paciente. Numa lista de 30 leitos isso torna a leitura por áudio inutilizável.
 *
 * O custo aceito em troca: um render a mais ao cruzar o breakpoint, e a
 * necessidade de `matchMedia` existir (jsdom não o implementa — já há stub em
 * `setupTests.ts`, com `matches: false`, então o teste vê a tabela).
 */
const CONSULTA = '(max-width: 1023.98px)';

export function useTelaEstreita(): boolean {
  const [estreita, setEstreita] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(CONSULTA).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia(CONSULTA);
    const aoMudar = (e: MediaQueryListEvent) => setEstreita(e.matches);

    // O valor pode ter mudado entre o `useState` inicial e este efeito —
    // rotação de tablet durante o carregamento é o caso real.
    setEstreita(mq.matches);
    mq.addEventListener('change', aoMudar);
    return () => mq.removeEventListener('change', aoMudar);
  }, []);

  return estreita;
}
