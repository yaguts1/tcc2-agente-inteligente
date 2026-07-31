/**
 * Inscrição do aparelho em notificações que sobrevivem à aba fechada.
 *
 * O que existia: um beep WebAudio e a Notification API, ambos exigindo a aba
 * viva. Fechada a aba — ou o navegador — o sistema ficava sem nenhum canal de
 * saída, exatamente durante a madrugada, que é quando ninguém está olhando a
 * tela e quando um alerta ignorado custa mais caro.
 *
 * O estado tem QUATRO valores, e a distinção não é preciosismo. "Indisponível"
 * e "negado" pedem coisas diferentes de quem opera: no primeiro caso não há o
 * que fazer no aparelho, no segundo a permissão precisa ser reativada nas
 * configurações do navegador — e um botão que tenta de novo depois de negado
 * não faz nada, porque o navegador não pergunta duas vezes.
 */
import { useCallback, useEffect, useState } from 'react';
import { pushApi } from '../lib/api';

export type EstadoPush =
  /** Navegador sem service worker/Push, ou servidor sem VAPID configurado. */
  | 'indisponivel'
  /** Dá para inscrever, e ainda não se inscreveu. */
  | 'disponivel'
  /** Inscrito e recebendo. */
  | 'ativo'
  /** O usuário negou a permissão. Só as configurações do navegador revertem. */
  | 'negado';

/**
 * A chave VAPID viaja em base64url e a API do navegador quer `Uint8Array`.
 * Sem a conversão, `subscribe()` falha com um erro que não menciona a chave.
 */
function base64UrlParaBytes(base64: string): Uint8Array {
  const preenchido = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
  const normalizado = preenchido.replace(/-/g, '+').replace(/_/g, '/');
  const cru = atob(normalizado);
  return Uint8Array.from(cru, (c) => c.charCodeAt(0));
}

function suportado(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

export function useWebPush() {
  const [estado, setEstado] = useState<EstadoPush>('indisponivel');
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (!suportado()) return;
    if (Notification.permission === 'denied') {
      setEstado('negado');
      return;
    }

    let cancelado = false;
    (async () => {
      try {
        const chave = await pushApi.chavePublica();
        if (cancelado) return;
        if (!chave.configurado) {
          // O servidor não tem VAPID. Distinto de "o navegador não suporta",
          // embora a tela trate os dois como indisponível — quem lê o log
          // precisa saber qual dos dois é.
          setEstado('indisponivel');
          return;
        }

        const registro = await navigator.serviceWorker.ready;
        const inscricao = await registro.pushManager.getSubscription();
        if (cancelado) return;
        setEstado(inscricao ? 'ativo' : 'disponivel');
      } catch {
        // Falhar aqui não pode derrubar a tela: notificação é uma camada extra
        // sobre um painel que já funciona sozinho.
        if (!cancelado) setEstado('indisponivel');
      }
    })();

    return () => {
      cancelado = true;
    };
  }, []);

  const ativar = useCallback(async () => {
    if (!suportado()) return;
    setOcupado(true);
    try {
      const permissao = await Notification.requestPermission();
      if (permissao !== 'granted') {
        setEstado(permissao === 'denied' ? 'negado' : 'disponivel');
        return;
      }

      const chave = await pushApi.chavePublica();
      if (!chave.configurado || !chave.chave_publica) {
        setEstado('indisponivel');
        return;
      }

      const registro = await navigator.serviceWorker.ready;
      const inscricao = await registro.pushManager.subscribe({
        // Obrigatório e sempre `true` nos navegadores atuais: nenhum aceita
        // push silencioso. Declarar explicitamente evita um erro obscuro.
        userVisibleOnly: true,
        applicationServerKey: base64UrlParaBytes(chave.chave_publica),
      });

      const json = inscricao.toJSON() as {
        endpoint?: string;
        keys?: { p256dh?: string; auth?: string };
      };
      await pushApi.inscrever({
        endpoint: json.endpoint ?? '',
        p256dh: json.keys?.p256dh ?? '',
        auth: json.keys?.auth ?? '',
      });
      setEstado('ativo');
    } catch {
      setEstado('disponivel');
    } finally {
      setOcupado(false);
    }
  }, []);

  const desativar = useCallback(async () => {
    if (!suportado()) return;
    setOcupado(true);
    try {
      const registro = await navigator.serviceWorker.ready;
      const inscricao = await registro.pushManager.getSubscription();
      if (inscricao) {
        const json = inscricao.toJSON() as { endpoint?: string };
        // Avisa o servidor ANTES de cancelar no navegador. Na ordem inversa,
        // uma falha de rede deixaria o servidor mandando push para um endpoint
        // que já não existe — e ele só descobriria pelo 410, no próximo ciclo.
        await pushApi.desinscrever(json.endpoint ?? '').catch(() => undefined);
        await inscricao.unsubscribe();
      }
      setEstado('disponivel');
    } finally {
      setOcupado(false);
    }
  }, []);

  return { estado, ocupado, ativar, desativar };
}
