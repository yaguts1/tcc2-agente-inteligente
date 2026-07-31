/*
 * Service worker: o único código desta aplicação que roda com a aba fechada.
 *
 * Antes, o aviso era um beep WebAudio e a Notification API, ambos exigindo a
 * aba viva. Pior, o tratamento da suspensão de autoplay do Chrome desiste em
 * silêncio quando o navegador recusa — engenharia correta, e clinicamente
 * significa que o alerta pode nunca soar sem que ninguém saiba.
 *
 * Deliberadamente MÍNIMO. Não faz cache de nada.
 *
 * Cache aqui seria ativamente perigoso: um service worker que serve uma versão
 * antiga da lista de alertas mostra pacientes já atendidos como pendentes, e
 * pacientes que escalaram como normais — e o faz de forma persistente, porque
 * sobrevive ao recarregamento da página. O modo de falha de "dado clínico
 * velho apresentado como atual" é exatamente o que o resto deste sistema
 * combate. Se um dia houver modo offline, ele terá que ser projetado, e não
 * herdado de um cache genérico.
 */

self.addEventListener('install', () => {
  // Assume o controle sem esperar a aba antiga fechar. Sem isto, a primeira
  // instalação só passa a valer no próximo carregamento — e quem acabou de
  // ativar as notificações não receberia a primeira.
  self.skipWaiting();
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(self.clients.claim());
});

self.addEventListener('push', (evento) => {
  let dados = {};
  try {
    dados = evento.data ? evento.data.json() : {};
  } catch {
    // Payload ilegível não pode virar notificação silenciosa: o servidor achou
    // que tinha algo a dizer, e engolir isso reproduz o defeito que este
    // arquivo existe para corrigir.
    dados = { titulo: 'Alerta de reposicionamento', corpo: 'Abra o painel' };
  }

  const nivel = dados.nivel || 'atencao';

  evento.waitUntil(
    self.registration.showNotification(dados.titulo || 'Alerta', {
      body: dados.corpo || '',
      icon: '/TCC/icon-alert.png',
      badge: '/TCC/badge-alert.png',
      // `tag` por nível, e não por alerta: um alerta que escala de crítico para
      // violação SUBSTITUI a notificação anterior em vez de empilhar duas para
      // o mesmo paciente.
      tag: `upp-${dados.alertId || nivel}`,
      renotify: true,
      // `violacao` exige interação: a essa altura ninguém respondeu por três
      // janelas, e uma notificação que some sozinha depois de alguns segundos
      // teria a mesma eficácia de não existir.
      requireInteraction: nivel === 'violacao',
      // Vibração só nos dois níveis altos. No aparelho de bolso da enfermagem,
      // vibrar para tudo é o mesmo que não vibrar para nada.
      vibrate: nivel === 'normal' ? undefined : [200, 100, 200],
      data: { alertId: dados.alertId || null },
    }),
  );
});

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();

  evento.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((abas) => {
      // Reaproveita uma aba já aberta em vez de abrir outra. Abrir uma nova a
      // cada notificação deixaria a enfermagem com seis abas do mesmo painel
      // até o fim do plantão.
      for (const aba of abas) {
        if (aba.url.includes('/TCC') && 'focus' in aba) return aba.focus();
      }
      return self.clients.openWindow('/TCC/');
    }),
  );
});
