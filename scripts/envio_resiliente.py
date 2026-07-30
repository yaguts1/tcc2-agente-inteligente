"""Politica de entrega de amostras de sensor.

Vive separado do simulador porque e a MESMA regra que o firmware implementa
(firmware/esp32_replay/esp32_replay.ino) — e aqui ela pode ser testada, o que
no sketch C++ nao acontece sem hardware. Se a semantica mudar de um lado,
`tests/test_envio_resiliente.py` e o lugar de decidir qual dos dois esta certo.

A regra, em uma frase: **nao existe amostra perdida por falha temporaria**.
Uma amostra so sai da fila quando o servidor confirma o recebimento ou quando
recusa o conteudo em definitivo — e, nesse caso, o descarte e contado, nunca
silencioso.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from collections.abc import Callable


class Resultado(Enum):
    """Desfecho de uma tentativa de entrega."""

    ACK = "ack"
    TRANSIENTE = "transiente"
    PERMANENTE = "permanente"


def classificar(status: int | None) -> Resultado:
    """Traduz o status HTTP (ou None, para falha de conexao) em desfecho.

    401/403 sao TRANSIENTE de proposito: token errado e erro de configuracao,
    e o dispositivo deve se recuperar sozinho quando alguem corrigir. Pular as
    amostras nesse caso seria perda silenciosa de dado clinico — e perda logo
    no cenario em que TODAS as amostras falham.

    Os demais 4xx sao PERMANENTE: um payload que o servidor recusa (422) nunca
    vai passar, e insistir travaria a fila inteira atras dele.
    """
    if status is None:
        return Resultado.TRANSIENTE
    if 200 <= status < 300:
        return Resultado.ACK
    if status >= 500 or status in (408, 429, 401, 403):
        return Resultado.TRANSIENTE
    if status >= 400:
        return Resultado.PERMANENTE
    return Resultado.TRANSIENTE


@dataclass
class PoliticaRetry:
    """Backoff exponencial com teto e jitter.

    `tentativas_max` e o TOTAL de tentativas, contando a primeira — nao o
    numero de repeticoes depois dela. `0` significa infinito, que e o padrao: o
    teto do backoff (`backoff_max_s`) ja garante que o dispositivo nao martele
    o servidor — ele passa a tentar uma vez por minuto ate a API voltar.
    """

    base_s: float = 0.5
    backoff_max_s: float = 60.0
    tentativas_max: int = 0
    jitter: bool = True
    _rng: random.Random = field(default_factory=random.Random)

    def espera(self, tentativa: int) -> float:
        """Segundos a aguardar antes da tentativa de indice `tentativa` (0-based)."""
        atraso = min(self.base_s * (2**tentativa), self.backoff_max_s)
        if self.jitter:
            atraso += self._rng.uniform(0, atraso / 4)
        return atraso

    def desistir(self, tentativa: int) -> bool:
        """`tentativa` e o indice 0-based da que acabou de acontecer."""
        return self.tentativas_max > 0 and (tentativa + 1) >= self.tentativas_max


@dataclass
class Contadores:
    entregues: int = 0
    descartados: int = 0
    tentativas: int = 0


def entregar(
    enviar: Callable[[], int | None],
    politica: PoliticaRetry,
    contadores: Contadores,
    *,
    dormir: Callable[[float], None] = time.sleep,
    registrar: Callable[[str], None] = print,
) -> Resultado:
    """Entrega uma amostra, repetindo enquanto a falha for temporaria.

    `enviar` devolve o status HTTP, ou None se a conexao falhou. Devolve o
    desfecho final: ACK, PERMANENTE (recusado e contado) ou TRANSIENTE (so
    quando ha limite de tentativas configurado e ele se esgotou — a amostra
    NAO foi entregue e cabe a quem chamou preserva-la).
    """
    tentativa = 0
    while True:
        contadores.tentativas += 1
        resultado = classificar(enviar())

        if resultado is Resultado.ACK:
            contadores.entregues += 1
            return resultado

        if resultado is Resultado.PERMANENTE:
            contadores.descartados += 1
            registrar("[DESCARTE] amostra recusada em definitivo pelo servidor; seguindo")
            return resultado

        if politica.desistir(tentativa):
            registrar("[ERRO] limite de tentativas atingido; amostra preservada")
            return resultado

        atraso = politica.espera(tentativa)
        registrar(f"[RETRY] falha temporaria; nova tentativa em {atraso:.1f}s")
        dormir(atraso)
        tentativa += 1
