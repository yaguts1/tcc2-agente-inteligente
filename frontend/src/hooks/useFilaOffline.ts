/**
 * Drena a fila de ações que a rede engoliu.
 *
 * Reenvia quando o navegador volta a ficar online, e periodicamente enquanto
 * houver pendências — o evento `online` sozinho não basta: ele dispara quando a
 * interface de rede sobe, e no Wi-Fi hospitalar isso acontece antes de o
 * servidor estar de fato alcançável (portal cativo, roteamento entre APs).
 * Confiar só nele deixaria a fila parada com o aparelho "online".
 *
 * O reenvio é seguro porque `alterar_status_alerta` já é idempotente e
 * `alert_id` é chave natural `(paciente, início)` — ver `lib/filaOffline.ts`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { ApiException, alertsApi } from '../lib/api';
import type { MotivoFechamento } from '../lib/api';
import {
  MAX_TENTATIVAS,
  type AcaoPendente,
  listar,
  registrarTentativa,
  remover,
} from '../lib/filaOffline';

/** Enquanto houver pendências, tenta de novo neste intervalo. */
const INTERVALO_MS = 20_000;

export function useFilaOffline(aoSincronizar?: () => void | Promise<void>) {
  const [pendentes, setPendentes] = useState<AcaoPendente[]>([]);
  // `useRef` e não state: `drenar` não pode depender do valor para evitar
  // recriar o callback, e duas execuções simultâneas reenviariam tudo em
  // dobro — inofensivo pela idempotência, mas gastaria rede e produziria
  // toasts duplicados.
  const drenando = useRef(false);

  const recarregar = useCallback(async () => {
    setPendentes(await listar());
  }, []);

  const drenar = useCallback(async () => {
    if (drenando.current) return;
    drenando.current = true;
    try {
      const fila = await listar();
      if (fila.length === 0) return;

      let enviadas = 0;
      let descartadas = 0;

      for (const acao of fila) {
        try {
          if (acao.tipo === 'acknowledge') {
            await alertsApi.acknowledge(acao.alertId);
          } else {
            await alertsApi.complete(acao.alertId, acao.motivo as MotivoFechamento);
          }
          await remover(acao.id);
          enviadas += 1;
        } catch (erro) {
          // Erro do SERVIDOR (4xx) não melhora com repetição: o alerta já foi
          // fechado por outra pessoa, ou o estado não permite a transição.
          // Insistir manteria a entrada viva para sempre e o indicador de
          // pendências nunca zeraria — o que treina a pessoa a ignorá-lo, e aí
          // ele não serve para o caso real.
          const respostaDoServidor =
            erro instanceof ApiException && erro.status >= 400 && erro.status < 500;

          if (respostaDoServidor || acao.tentativas + 1 >= MAX_TENTATIVAS) {
            await remover(acao.id);
            descartadas += 1;
          } else {
            await registrarTentativa(acao);
            // Falha de rede: para o laço inteiro. Continuar tentando as
            // seguintes só gastaria tempo — elas vão falhar igual, e a ordem
            // importa (é a ordem em que a pessoa agiu).
            break;
          }
        }
      }

      if (enviadas > 0) {
        toast.success(
          enviadas === 1
            ? 'Ação pendente sincronizada'
            : `${enviadas} ações pendentes sincronizadas`,
        );
        await aoSincronizar?.();
      }
      if (descartadas > 0) {
        // Descarte precisa ser DITO. Uma ação que sumiu em silêncio é
        // exatamente o problema que esta fila veio resolver.
        toast.warning(
          descartadas === 1
            ? 'Uma ação pendente não pôde ser aplicada (o alerta pode ter sido resolvido por outra pessoa)'
            : `${descartadas} ações pendentes não puderam ser aplicadas`,
        );
      }
    } finally {
      drenando.current = false;
      await recarregar();
    }
  }, [aoSincronizar, recarregar]);

  useEffect(() => {
    void recarregar();

    const aoVoltar = () => void drenar();
    window.addEventListener('online', aoVoltar);

    // O `online` do navegador é otimista: dispara quando a interface sobe, não
    // quando o servidor responde. O intervalo cobre esse vão.
    const timer = window.setInterval(() => {
      if (navigator.onLine) void drenar();
    }, INTERVALO_MS);

    return () => {
      window.removeEventListener('online', aoVoltar);
      window.clearInterval(timer);
    };
  }, [drenar, recarregar]);

  return { pendentes, drenar, recarregar };
}
