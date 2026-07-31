/**
 * Fila de ações que a rede engoliu.
 *
 * Wi-Fi hospitalar cai em corredor, escada e elevador — não é caso de borda, é
 * a topologia. Quem marcou quatro pacientes numa zona morta perdia os quatro,
 * e **sem saber quais**: o `toast.error` some, a lista é revertida pelo
 * `fetchAlerts()` do catch, e trinta segundos depois não há nada na tela
 * indicando que aquelas ações existiram.
 *
 * O custo real não é o clique perdido. É que a enfermeira acredita ter
 * registrado o reposicionamento, e o prontuário diz que não — a discrepância
 * aparece na auditoria, semanas depois, como se ela não tivesse feito o
 * trabalho.
 *
 * A MAIOR PARTE DO TRABALHO JÁ EXISTIA, e é o que torna isto seguro:
 *
 *   - `alert_id` é chave natural `(paciente, início)`, então reenviar a mesma
 *     ação não pode atingir outro alerta;
 *   - `alterar_status_alerta` já é idempotente no servidor — reconhecer duas
 *     vezes o mesmo alerta é um no-op, não um erro nem uma duplicata.
 *
 * Sem essas duas, uma fila de reenvio seria perigosa: fabricaria registros
 * clínicos duplicados a cada reconexão.
 *
 * IndexedDB e não `localStorage`: o `localStorage` é síncrono e bloqueia a
 * thread de UI, e tem cota pequena. Mais importante, ele não sobrevive bem a
 * várias abas escrevendo ao mesmo tempo — e o tablet da ala fica com o painel
 * aberto o dia inteiro enquanto alguém abre outra aba no celular.
 */

const BANCO = 'upp-fila-offline';
const LOJA = 'acoes';
const VERSAO = 1;

export interface AcaoPendente {
  /** Gerado no cliente. Identifica a ENTRADA da fila, não o alerta. */
  id: string;
  tipo: 'acknowledge' | 'complete';
  alertId: string;
  motivo?: string;
  /** Quando a pessoa agiu — não quando a fila conseguiu enviar. */
  criadaEm: number;
  tentativas: number;
}

function abrir(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const pedido = indexedDB.open(BANCO, VERSAO);
    pedido.onupgradeneeded = () => {
      const db = pedido.result;
      if (!db.objectStoreNames.contains(LOJA)) {
        db.createObjectStore(LOJA, { keyPath: 'id' });
      }
    };
    pedido.onsuccess = () => resolve(pedido.result);
    pedido.onerror = () => reject(pedido.error);
  });
}

function comLoja<T>(
  modo: IDBTransactionMode,
  operacao: (loja: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return abrir().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const transacao = db.transaction(LOJA, modo);
        const pedido = operacao(transacao.objectStore(LOJA));
        pedido.onsuccess = () => resolve(pedido.result);
        pedido.onerror = () => reject(pedido.error);
        transacao.oncomplete = () => db.close();
      }),
  );
}

export function disponivel(): boolean {
  return typeof indexedDB !== 'undefined';
}

export async function enfileirar(
  acao: Omit<AcaoPendente, 'id' | 'criadaEm' | 'tentativas'>,
): Promise<AcaoPendente | null> {
  if (!disponivel()) return null;

  const pendentes = await listar();
  // Uma entrada por (tipo, alerta). Enfileirar a mesma ação duas vezes é o que
  // acontece quando a pessoa toca de novo achando que não pegou — e a segunda
  // entrada não acrescenta nada, porque o servidor é idempotente. Guardá-la só
  // faria a fila reportar "2 pendentes" para uma decisão só.
  const jaExiste = pendentes.find(
    (p) => p.alertId === acao.alertId && p.tipo === acao.tipo,
  );
  if (jaExiste) return jaExiste;

  const entrada: AcaoPendente = {
    ...acao,
    id: `${acao.tipo}:${acao.alertId}:${Date.now()}`,
    criadaEm: Date.now(),
    tentativas: 0,
  };
  await comLoja('readwrite', (loja) => loja.put(entrada));
  return entrada;
}

export async function listar(): Promise<AcaoPendente[]> {
  if (!disponivel()) return [];
  try {
    const todas = await comLoja<AcaoPendente[]>('readonly', (loja) => loja.getAll());
    // Mais antigas primeiro: a ordem em que a pessoa agiu é a ordem em que o
    // prontuário deve registrar.
    return todas.sort((a, b) => a.criadaEm - b.criadaEm);
  } catch {
    // IndexedDB indisponível (modo privativo em alguns navegadores, cota
    // esgotada). A fila deixa de funcionar; a aplicação não.
    return [];
  }
}

export async function remover(id: string): Promise<void> {
  if (!disponivel()) return;
  await comLoja('readwrite', (loja) => loja.delete(id));
}

export async function registrarTentativa(entrada: AcaoPendente): Promise<void> {
  if (!disponivel()) return;
  await comLoja('readwrite', (loja) =>
    loja.put({ ...entrada, tentativas: entrada.tentativas + 1 }),
  );
}

export async function limpar(): Promise<void> {
  if (!disponivel()) return;
  await comLoja('readwrite', (loja) => loja.clear());
}

/**
 * Tentativas antes de desistir de uma entrada.
 *
 * O limite existe porque nem toda falha é de rede: um alerta que o servidor
 * recusa com 409 (outra pessoa já fechou) falharia para sempre, e uma entrada
 * imortal na fila faria o indicador de pendências nunca zerar — o que treina a
 * pessoa a ignorá-lo, e aí ele não serve para o caso real.
 */
export const MAX_TENTATIVAS = 5;
