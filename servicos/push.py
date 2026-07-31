"""Web Push: o aviso que sobrevive a aba fechada.

O que existia antes: um beep WebAudio e a Notification API, ambos exigindo a
aba viva (`useCriticalAlerts`). O tratamento da suspensao de autoplay do Chrome
DESISTE EM SILENCIO quando o navegador recusa — engenharia correta, e
clinicamente significa que o aviso pode nunca soar sem que ninguem saiba.

Com a escada de escalonamento (4.2) o buraco ficou maior: um alerta que passa
para `violacao` as 04:00 agora TEM o que avisar, e nao tinha por onde.

TRES DECISOES QUE VALE REGISTRAR:

1. **Envio por TRANSICAO, nao por estado.** O loop de fundo roda a cada minuto.
   Notificar "ha alerta critico" a cada ciclo e a maneira mais rapida de fazer a
   equipe desligar as notificacoes do navegador — e uma vez desligadas, elas nao
   voltam. `push_nivel_notificado` guarda o ultimo nivel avisado por alerta, e
   so a SUBIDA dispara. E o mesmo criterio que o loop do watchdog ja usa para
   log, e o mesmo que a tela usa para o beep.

2. **A mensagem carrega leito e sitio, nao so "ha um alerta".** Uma notificacao
   que obriga a abrir o aplicativo para saber do que se trata e uma interrupcao
   sem informacao. "202-B · trocanter D · ha 3h" decide sozinha se vale
   levantar.

3. **Sem VAPID configurado, o modulo fica INERTE e diz isso alto no boot.** Nao
   levanta: derrubar a aplicacao inteira porque o push nao foi configurado
   trocaria uma funcionalidade ausente por um servico ausente. Mas tambem nao
   pode falhar calado, que e o defeito que este modulo veio corrigir.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def chave_publica() -> str | None:
    """Chave VAPID publica, que o navegador precisa para se inscrever."""
    return os.getenv("VAPID_PUBLIC_KEY") or None


def _chave_privada() -> str | None:
    return os.getenv("VAPID_PRIVATE_KEY") or None


def _contato() -> str:
    # O servico de push exige um contato para avisar sobre problemas de entrega.
    return os.getenv("VAPID_SUBJECT") or "mailto:ti@exemplo.invalido"


def configurado() -> bool:
    return bool(chave_publica() and _chave_privada())


def avisar_se_desconfigurado() -> None:
    """Chamado no boot. Ver a decisao 3 no cabecalho."""
    if configurado():
        return
    logger.warning(
        "push_desconfigurado",
        motivo=(
            "VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY ausentes: nenhuma notificacao "
            "sobrevive a aba fechada. Gere com "
            "`python -m scripts.gerar_chaves_vapid`."
        ),
    )


class ResultadoEnvio:
    """Quantos envios funcionaram, e quais inscricoes morreram.

    As mortas importam tanto quanto as vivas: o servico de push devolve 404/410
    quando o aparelho desinstalou o app ou revogou a permissao, e sem remove-las
    a tabela so cresce e cada ciclo gasta tempo entregando para telas que nao
    existem mais.
    """

    def __init__(self) -> None:
        self.enviados = 0
        self.falhas = 0
        self.mortas: list[str] = []


def enviar(inscricoes: list[dict[str, Any]], payload: dict[str, Any]) -> ResultadoEnvio:
    """Entrega `payload` a cada inscricao. Nunca levanta."""
    resultado = ResultadoEnvio()
    if not configurado() or not inscricoes:
        return resultado

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        # Dependencia opcional. Sem ela o resto do sistema funciona igual, e o
        # aviso explica por que nenhuma notificacao chega — sem isso, a
        # investigacao comecaria pelo navegador.
        logger.warning(
            "push_sem_biblioteca",
            motivo="pywebpush nao instalado; nenhuma notificacao sera enviada",
        )
        return resultado

    corpo = json.dumps(payload, ensure_ascii=False)
    for inscricao in inscricoes:
        try:
            webpush(
                subscription_info={
                    "endpoint": inscricao["endpoint"],
                    "keys": {"p256dh": inscricao["p256dh"], "auth": inscricao["auth"]},
                },
                data=corpo,
                vapid_private_key=_chave_privada(),
                vapid_claims={"sub": _contato()},
                timeout=10,
            )
            resultado.enviados += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                # Inscricao morta: o aparelho desinstalou o app ou revogou a
                # permissao. Nao e erro operacional, e limpeza.
                resultado.mortas.append(inscricao["endpoint"])
            else:
                resultado.falhas += 1
                logger.warning(
                    "push_falhou",
                    status=status,
                    endpoint=str(inscricao["endpoint"])[:60],
                )
        except Exception as exc:
            # Rede, DNS, timeout. Uma inscricao problematica nao pode impedir a
            # entrega para as outras — e a que mais importa pode ser a proxima.
            resultado.falhas += 1
            logger.warning("push_erro", erro=str(exc)[:200])

    return resultado


# Texto da notificacao ------------------------------------------------------

_TITULO_POR_NIVEL = {
    "atencao": "Reposicionamento atrasado",
    "critico": "Atraso crítico",
    "violacao": "Sem resposta há 3 janelas",
}


def montar_payload(alerta: dict[str, Any]) -> dict[str, Any]:
    """A mensagem que chega no aparelho.

    Carrega leito, sitio e tempo em aberto. Uma notificacao que obriga a abrir o
    aplicativo para saber do que se trata e uma interrupcao sem informacao —
    e a 4h da manha a diferenca entre isso e "202-B · trocanter D · ha 3h" e a
    diferenca entre levantar e nao levantar.
    """
    leito = " / ".join(p for p in (alerta.get("room"), alerta.get("bed")) if p) or "sem leito"
    partes = [leito]
    if alerta.get("site"):
        partes.append(str(alerta["site"]).replace("_", " "))
    minutos = int(alerta.get("minutesOpen") or 0)
    partes.append(f"há {minutos // 60}h{minutos % 60:02d}" if minutos >= 60 else f"há {minutos}min")

    return {
        "titulo": _TITULO_POR_NIVEL.get(str(alerta.get("escalationLevel")), "Alerta"),
        "corpo": " · ".join(partes),
        "nivel": alerta.get("escalationLevel"),
        # Para o service worker abrir a tela certa ao ser tocado.
        "alertId": alerta.get("id"),
        "paciente": alerta.get("patientName"),
    }
