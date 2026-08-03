"""Onde o filtro de qualidade guarda o que precisa lembrar entre amostras.

POR QUE ISTO DEIXOU DE SER UM DICIONÁRIO DE MÓDULO
---------------------------------------------------
`quality/filtro.py` mantinha duas estruturas em variáveis globais: o cache de
deduplicação e o buffer de reordenação (jitter). Enquanto houver um processo só,
funciona. Com uma réplica a mais, as duas quebram — e de formas diferentes:

* **dedup** vira desperdício: a mesma amostra chegando em réplicas diferentes é
  processada duas vezes. A chave primária da `grade` recusa a duplicata, então
  não corrompe — custa trabalho, não dado;

* **buffer de reordenação** vira *perda de correção*. Ele existe porque amostras
  chegam fora de ordem e precisam ser reordenadas antes de irem ao motor. Com
  duas réplicas, cada uma reordena metade contra a própria janela, e amostras
  que deveriam se reordenar entre si nunca se encontram. Subir uma réplica
  desliga em silêncio a correção que o buffer existe para fazer.

E há um terceiro efeito, que foi o que apareceu primeiro na prática: **estado em
processo não é limpável de fora**. Repetir uma demonstração exigia reiniciar o
container inteiro, porque apagar as linhas do banco não alcançava o dedup — o
segundo envio das mesmas amostras era descartado como duplicata, com ACK, e nada
aparecia na tela.

O PADRÃO
--------
Igual ao de `servicos/processamento_incremental.py`: uma interface, um backend
em memória (o padrão, comportamento idêntico ao histórico) e um backend Redis
escolhido por `REDIS_URL`. Sem Redis configurado, nada muda para quem roda uma
instância só.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)

# Quantas chaves de dedup lembrar por dispositivo. Mesmo valor do `deque` que
# existia antes — não é arbitrário: cobre horas de amostragem por aparelho, e o
# custo de esquecer é reprocessar uma amostra que a PK da grade já recusaria.
LIMITE_DEDUP = 2048

# TTL das chaves no Redis. Um dispositivo removido não pode deixar lixo
# acumulando para sempre num armazenamento compartilhado — em processo isso se
# resolvia sozinho quando a instância reiniciava.
TTL_SEGUNDOS = 60 * 60 * 24


class EstadoDoFiltro(Protocol):
    """O que o filtro precisa lembrar. Duas implementações abaixo."""

    def ja_visto(self, device_id: str, chave: str) -> bool: ...
    def registrar(self, device_id: str, chave: str) -> None: ...
    def guardar(self, device_id: str, ordem: float, evento: dict) -> None: ...
    def liberar_ate(self, device_id: str, limite: float) -> list[dict]: ...
    def pendentes(self, device_id: str) -> int: ...
    def drenar(self, device_id: str) -> list[dict]: ...
    def dispositivos(self) -> list[str]: ...
    def limpar(self) -> None: ...


class EstadoEmMemoria:
    """O comportamento histórico, sem mudança nenhuma.

    Continua sendo o padrão: uma instalação de uma instância não deve pagar
    latência de rede nem depender de outro serviço para funcionar.
    """

    def __init__(self) -> None:
        self._dedup: dict[str, list[str]] = {}
        self._buffer: dict[str, list[tuple[float, int, dict]]] = {}
        self._contador = itertools.count()

    def ja_visto(self, device_id: str, chave: str) -> bool:
        return chave in self._dedup.get(device_id, ())

    def registrar(self, device_id: str, chave: str) -> None:
        fila = self._dedup.setdefault(device_id, [])
        fila.append(chave)
        if len(fila) > LIMITE_DEDUP:
            del fila[: len(fila) - LIMITE_DEDUP]

    def guardar(self, device_id: str, ordem: float, evento: dict) -> None:
        import heapq

        # O contador desempata timestamps iguais e mantém a ordem de CHEGADA
        # entre eles — sem ele, `heapq` tentaria comparar os dicionários.
        heapq.heappush(self._buffer.setdefault(device_id, []), (ordem, next(self._contador), evento))

    def liberar_ate(self, device_id: str, limite: float) -> list[dict]:
        import heapq

        heap = self._buffer.get(device_id)
        prontos: list[dict] = []
        while heap and heap[0][0] <= limite:
            prontos.append(heapq.heappop(heap)[2])
        return prontos

    def pendentes(self, device_id: str) -> int:
        return len(self._buffer.get(device_id, ()))

    def drenar(self, device_id: str) -> list[dict]:
        import heapq

        heap = self._buffer.pop(device_id, [])
        return [heapq.heappop(heap)[2] for _ in range(len(heap))]

    def dispositivos(self) -> list[str]:
        return list(self._buffer.keys())

    def limpar(self) -> None:
        self._dedup.clear()
        self._buffer.clear()


class EstadoNoRedis:
    """O mesmo estado, compartilhado entre réplicas.

    Duas estruturas por dispositivo:

    * `filtro:dedup:{device}` — SET com as chaves já vistas. SET e não lista:
      a pergunta é "já vi?", e é o Redis que deve responder isso em O(1) sem
      trazer nada pela rede;
    * `filtro:buffer:{device}` — ZSET com score = instante da amostra. Liberar
      "tudo até T" vira um `zrangebyscore`, que é exatamente a operação que o
      heap fazia localmente.

    A liberação usa uma transação (`MULTI`): entre ler os elementos e removê-los,
    outra réplica poderia ler os MESMOS e as duas entregariam a amostra ao motor.
    """

    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.from_url(url, decode_responses=True)
        self._contador = itertools.count()

    def _k_dedup(self, device_id: str) -> str:
        return f"filtro:dedup:{device_id}"

    def _k_buffer(self, device_id: str) -> str:
        return f"filtro:buffer:{device_id}"

    def ja_visto(self, device_id: str, chave: str) -> bool:
        return bool(self._r.sismember(self._k_dedup(device_id), chave))

    def registrar(self, device_id: str, chave: str) -> None:
        k = self._k_dedup(device_id)
        pipe = self._r.pipeline()
        pipe.sadd(k, chave)
        pipe.expire(k, TTL_SEGUNDOS)
        pipe.execute()
        # Poda barata: só quando o conjunto passa do limite, e removendo um lote
        # arbitrário. A ordem de remoção não importa — o que se perde é a memória
        # de uma amostra ANTIGA, e reprocessá-la é inofensivo (a PK da grade
        # recusa). O que não pode é crescer sem teto.
        if self._r.scard(k) > LIMITE_DEDUP:
            excedente = self._r.scard(k) - LIMITE_DEDUP
            velhas = self._r.srandmember(k, excedente)
            if velhas:
                self._r.srem(k, *velhas)

    def guardar(self, device_id: str, ordem: float, evento: dict) -> None:
        k = self._k_buffer(device_id)
        # O contador entra no MEMBRO porque o ZSET é um conjunto: duas amostras
        # com o mesmo conteúdo e o mesmo instante colidiriam e uma sumiria.
        membro = json.dumps({"n": next(self._contador), "evt": evento}, ensure_ascii=False)
        pipe = self._r.pipeline()
        pipe.zadd(k, {membro: ordem})
        pipe.expire(k, TTL_SEGUNDOS)
        pipe.execute()

    def _extrair(self, membros: list[str]) -> list[dict]:
        eventos = []
        for m in membros:
            try:
                eventos.append(json.loads(m)["evt"])
            except (ValueError, KeyError):
                logger.warning("buffer_membro_ilegivel", membro=m[:120])
        return eventos

    def liberar_ate(self, device_id: str, limite: float) -> list[dict]:
        k = self._k_buffer(device_id)
        with self._r.pipeline() as pipe:
            while True:
                try:
                    # WATCH + MULTI: sem isto, duas réplicas leriam os mesmos
                    # membros e ambas os entregariam ao motor — a amostra
                    # apareceria duas vezes no processamento.
                    pipe.watch(k)
                    membros = pipe.zrangebyscore(k, "-inf", limite)
                    if not membros:
                        pipe.unwatch()
                        return []
                    pipe.multi()
                    pipe.zrem(k, *membros)
                    pipe.execute()
                    return self._extrair(membros)
                except Exception as exc:  # WatchError e afins
                    if exc.__class__.__name__ != "WatchError":
                        raise
                    continue

    def pendentes(self, device_id: str) -> int:
        return int(self._r.zcard(self._k_buffer(device_id)))

    def drenar(self, device_id: str) -> list[dict]:
        k = self._k_buffer(device_id)
        with self._r.pipeline() as pipe:
            pipe.zrange(k, 0, -1)
            pipe.delete(k)
            membros, _ = pipe.execute()
        return self._extrair(membros)

    def dispositivos(self) -> list[str]:
        return [c.split(":", 2)[2] for c in self._r.scan_iter(match="filtro:buffer:*")]

    def limpar(self) -> None:
        chaves = list(self._r.scan_iter(match="filtro:dedup:*")) + list(
            self._r.scan_iter(match="filtro:buffer:*")
        )
        if chaves:
            self._r.delete(*chaves)


def criar_estado(redis_url: str | None) -> EstadoDoFiltro:
    """Redis quando configurado; memória quando não.

    Falha ao conectar NÃO derruba a ingestão: cai para memória e avisa alto. Uma
    ala parar de receber amostra porque o Redis reiniciou seria trocar um
    problema de escala por um de disponibilidade — e o modo memória é o
    comportamento que a instalação tinha até ontem.
    """
    if not redis_url:
        return EstadoEmMemoria()
    try:
        estado = EstadoNoRedis(redis_url)
        estado._r.ping()
        logger.info("filtro_estado_redis", url=redis_url.split("@")[-1])
        return estado
    except Exception as exc:
        logger.error(
            "filtro_estado_redis_indisponivel",
            erro=str(exc),
            consequencia="dedup e buffer voltam a ser por processo; nao suba replicas assim",
        )
        return EstadoEmMemoria()
