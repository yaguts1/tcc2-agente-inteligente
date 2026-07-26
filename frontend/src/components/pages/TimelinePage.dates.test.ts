import { describe, it, expect } from 'vitest';
import { limiteDoDiaLocal } from './TimelinePage';

/**
 * O filtro de datas da Timeline manda `start_ms`/`end_ms` (epoch absoluto) ao
 * backend. O que o usuario escolhe no <input type="date"> e um DIA no fuso
 * dele, entao a conversao tem que ser para a meia-noite LOCAL.
 *
 * O caminho antigo (`new Date('2026-07-26')` + `setHours(...)`) tratava a
 * string como meia-noite UTC: em America/Sao_Paulo isso ja e 25/07 21:00
 * local, e o setHours seguinte zerava o dia 25. O filtro devolvia o historico
 * do dia anterior e nenhum evento do dia pedido.
 */
describe('limiteDoDiaLocal', () => {
  it('inicio e a meia-noite LOCAL do dia escolhido', () => {
    const inicio = new Date(limiteDoDiaLocal('2026-07-26', 'inicio')!);

    expect(inicio.getFullYear()).toBe(2026);
    expect(inicio.getMonth()).toBe(6); // julho
    expect(inicio.getDate()).toBe(26); // o dia pedido, nao o anterior
    expect(inicio.getHours()).toBe(0);
    expect(inicio.getMinutes()).toBe(0);
  });

  it('fim e o ultimo instante LOCAL do dia escolhido', () => {
    const fim = new Date(limiteDoDiaLocal('2026-07-26', 'fim')!);

    expect(fim.getDate()).toBe(26);
    expect(fim.getHours()).toBe(23);
    expect(fim.getMinutes()).toBe(59);
    expect(fim.getSeconds()).toBe(59);
  });

  it('nao repete a interpretacao UTC que causava o desvio de um dia', () => {
    // A implementacao antiga, reproduzida: em fuso negativo cai no dia anterior.
    const antigo = new Date('2026-07-26');
    antigo.setHours(0, 0, 0, 0);

    const atual = limiteDoDiaLocal('2026-07-26', 'inicio')!;

    expect(new Date(atual).getDate()).toBe(26);
    if (new Date('2026-07-26T00:00:00Z').getTimezoneOffset() > 0) {
      // Fuso a oeste de Greenwich (o caso de America/Sao_Paulo): os dois
      // resultados TEM que divergir — e a divergencia e o bug.
      expect(atual).not.toBe(antigo.getTime());
      expect(antigo.getDate()).toBe(25);
    }
  });

  it('filtrar um unico dia cobre as 24 horas daquele dia', () => {
    const inicio = limiteDoDiaLocal('2026-02-10', 'inicio')!;
    const fim = limiteDoDiaLocal('2026-02-10', 'fim')!;

    expect(fim - inicio).toBe(24 * 60 * 60 * 1000 - 1);
  });

  it('data malformada nao vira um instante arbitrario', () => {
    expect(limiteDoDiaLocal('', 'inicio')).toBeUndefined();
    expect(limiteDoDiaLocal('26/07/2026', 'inicio')).toBeUndefined();
  });
});
