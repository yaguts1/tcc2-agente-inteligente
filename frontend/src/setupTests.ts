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
