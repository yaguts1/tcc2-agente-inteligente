/**
 * Liga e desliga a notificação que sobrevive à aba fechada.
 *
 * Os quatro estados são visualmente distintos de propósito. O caso que mais
 * importa é `negado`: uma vez que o usuário recusa a permissão, o navegador
 * NÃO pergunta de novo — um botão que continua oferecendo "ativar" ali seria
 * um botão que não faz nada, e a pessoa concluiria que o sistema está quebrado
 * quando o que falta é uma mudança nas configurações do navegador.
 *
 * `indisponivel` some da tela em vez de aparecer desabilitado. Não há ação
 * possível (ou o navegador não suporta, ou o servidor não tem VAPID), e um
 * controle morto ocupando espaço na barra lateral só ensina a ignorar aquela
 * região da interface.
 */
import { Bell, BellOff, BellRing } from 'lucide-react';
import { Button } from '../ui/button';
import { Spinner } from '../shared/Spinner';
import { useWebPush } from '../../hooks/useWebPush';

export function BotaoDeNotificacao({ compacto = false }: { compacto?: boolean }) {
  const { estado, ocupado, ativar, desativar } = useWebPush();

  if (estado === 'indisponivel') return null;

  if (estado === 'negado') {
    return (
      <span
        className="flex items-center gap-2 text-xs text-muted-foreground"
        title="Reative nas configurações do navegador — ele não pergunta duas vezes"
      >
        <BellOff className="w-4 h-4" aria-hidden="true" />
        {!compacto && 'Notificações bloqueadas'}
      </span>
    );
  }

  const ativo = estado === 'ativo';

  return (
    <Button
      type="button"
      variant={ativo ? 'default' : 'outline'}
      size={compacto ? 'sm' : 'toque'}
      onClick={ativo ? desativar : ativar}
      disabled={ocupado}
      aria-pressed={ativo}
      title={
        ativo
          ? 'Recebendo avisos mesmo com a aba fechada'
          : 'Sem isto, o aviso só toca com esta aba aberta'
      }
    >
      {ocupado ? (
        <Spinner />
      ) : ativo ? (
        <BellRing className="w-4 h-4" aria-hidden="true" />
      ) : (
        <Bell className="w-4 h-4" aria-hidden="true" />
      )}
      {!compacto && <span className="ml-2">{ativo ? 'Avisos ligados' : 'Ligar avisos'}</span>}
    </Button>
  );
}
