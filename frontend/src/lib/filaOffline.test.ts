/**
 * A fila de ações que a rede engoliu.
 *
 * Wi-Fi hospitalar cai em corredor, escada e elevador — não é caso de borda, é
 * a topologia. Quem marcava quatro pacientes numa zona morta perdia os quatro,
 * e **sem saber quais**: o toast some, a lista é revertida, e trinta segundos
 * depois não há nada na tela indicando que aquelas ações existiram.
 *
 * O custo não é o clique perdido: é que a enfermeira acredita ter registrado o
 * reposicionamento e o prontuário diz que não — a discrepância aparece na
 * auditoria semanas depois, como se ela não tivesse feito o trabalho.
 */
import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  MAX_TENTATIVAS,
  enfileirar,
  limpar,
  listar,
  registrarTentativa,
  remover,
} from './filaOffline';

beforeEach(async () => {
  await limpar();
});

describe('enfileirar', () => {
  it('guarda a ação com o momento em que a pessoa agiu', async () => {
    const antes = Date.now();
    const entrada = await enfileirar({ tipo: 'complete', alertId: 'PAC-1__x' });

    expect(entrada).not.toBeNull();
    // `criadaEm` é quando a pessoa DECIDIU, não quando a fila conseguiu
    // enviar. É o horário que o prontuário deveria refletir.
    expect(entrada!.criadaEm).toBeGreaterThanOrEqual(antes);
    expect(entrada!.tentativas).toBe(0);
  });

  it('a mesma ação enfileirada duas vezes não vira duas entradas', async () => {
    // Acontece quando a pessoa toca de novo achando que não pegou. A segunda
    // não acrescenta nada — o servidor é idempotente — e guardá-la faria a
    // fila reportar "2 pendentes" para uma decisão só, o que sugere que algo
    // deu errado quando não deu.
    await enfileirar({ tipo: 'acknowledge', alertId: 'PAC-1__x' });
    await enfileirar({ tipo: 'acknowledge', alertId: 'PAC-1__x' });

    expect(await listar()).toHaveLength(1);
  });

  it('reconhecer e concluir o MESMO alerta são entradas distintas', async () => {
    // São decisões clínicas diferentes: uma diz "eu vi", a outra diz "eu agi".
    // Colapsá-las perderia o reconhecimento, que é o que alimenta o
    // tempo-até-ack.
    await enfileirar({ tipo: 'acknowledge', alertId: 'PAC-1__x' });
    await enfileirar({ tipo: 'complete', alertId: 'PAC-1__x' });

    expect(await listar()).toHaveLength(2);
  });

  it('preserva o motivo do fechamento', async () => {
    // Sem ele, o reenvio registraria "reposicionado" para um alerta encerrado
    // como "recusa do paciente" — e é essa afirmação que depois vira número de
    // adesão.
    await enfileirar({ tipo: 'complete', alertId: 'PAC-1__x', motivo: 'em_cirurgia' });

    expect((await listar())[0].motivo).toBe('em_cirurgia');
  });
});

describe('ordem', () => {
  it('a mais antiga primeiro', async () => {
    // A ordem em que a pessoa agiu é a ordem em que o prontuário deve
    // registrar.
    const a = await enfileirar({ tipo: 'acknowledge', alertId: 'A' });
    await new Promise((r) => setTimeout(r, 5));
    const b = await enfileirar({ tipo: 'acknowledge', alertId: 'B' });

    const fila = await listar();
    expect(fila.map((x) => x.alertId)).toEqual(['A', 'B']);
    expect(a!.criadaEm).toBeLessThanOrEqual(b!.criadaEm);
  });
});

describe('tentativas', () => {
  it('o contador sobe e a entrada sobrevive', async () => {
    await enfileirar({ tipo: 'acknowledge', alertId: 'PAC-1__x' });
    const [entrada] = await listar();

    await registrarTentativa(entrada);

    const [depois] = await listar();
    expect(depois.tentativas).toBe(1);
    expect(depois.id).toBe(entrada.id);
    // O momento da decisão não pode ser reescrito por uma tentativa de envio.
    expect(depois.criadaEm).toBe(entrada.criadaEm);
  });

  it('existe um teto', async () => {
    // Sem teto, uma entrada que o servidor sempre recusa fica imortal e o
    // indicador de pendências nunca zera — o que treina a pessoa a ignorá-lo,
    // e aí ele não serve para o caso real.
    expect(MAX_TENTATIVAS).toBeGreaterThan(0);
    expect(MAX_TENTATIVAS).toBeLessThan(20);
  });
});

describe('remoção', () => {
  it('remove só a entrada pedida', async () => {
    await enfileirar({ tipo: 'acknowledge', alertId: 'A' });
    await enfileirar({ tipo: 'acknowledge', alertId: 'B' });
    const [primeira] = await listar();

    await remover(primeira.id);

    const fila = await listar();
    expect(fila).toHaveLength(1);
    expect(fila[0].alertId).toBe('B');
  });
});

describe('persistência', () => {
  it('o dado não vive num array de módulo', async () => {
    // É o ponto de usar IndexedDB e não memória: a pessoa fecha o painel, sobe
    // de elevador, reabre — e as ações continuam lá.
    //
    // O teste abre o banco POR FORA do módulo. Se `listar()` lesse de uma
    // variável de módulo, o registro não estaria aqui — e a fila só
    // funcionaria enquanto a aba vivesse, que é exatamente o que ela veio
    // corrigir.
    await enfileirar({ tipo: 'complete', alertId: 'PAC-1__x', motivo: 'reposicionado' });

    const guardado = await new Promise<unknown[]>((resolve, reject) => {
      const pedido = indexedDB.open('upp-fila-offline', 1);
      pedido.onsuccess = () => {
        const db = pedido.result;
        const leitura = db.transaction('acoes', 'readonly').objectStore('acoes').getAll();
        leitura.onsuccess = () => {
          resolve(leitura.result);
          db.close();
        };
        leitura.onerror = () => reject(leitura.error);
      };
      pedido.onerror = () => reject(pedido.error);
    });

    expect(guardado).toHaveLength(1);
  });
});
