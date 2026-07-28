/**
 * Setup global do Vitest.
 *
 * Antes não havia `setupFiles`: cada teste precisaria importar os matchers na
 * mão, e não havia limpeza entre casos. Com apenas dois arquivos de teste isso
 * não incomodava; ao cobrir componentes, vazamento de estado entre casos vira
 * a principal fonte de teste instável.
 */
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// jsdom não implementa estas APIs, e componentes reais as usam. Sem os stubs,
// o teste quebra por motivo alheio ao que está sendo verificado.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
}

// Pointer capture: o Radix Select consulta estas três ao abrir o menu, e o
// jsdom não as implementa. Sem os stubs, qualquer teste que abra um `Select`
// morre com `target.hasPointerCapture is not a function` — um erro que não tem
// relação nenhuma com o que o teste verifica, e que aponta para o lugar errado.
if (!window.HTMLElement.prototype.hasPointerCapture) {
  window.HTMLElement.prototype.hasPointerCapture = vi.fn(() => false);
  window.HTMLElement.prototype.setPointerCapture = vi.fn();
  window.HTMLElement.prototype.releasePointerCapture = vi.fn();
}
