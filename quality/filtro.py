"""Filtros de qualidade para eventos recebidos dos dispositivos."""

from __future__ import annotations

import heapq
import itertools
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping

import structlog

from configuracao import config

logger = structlog.get_logger(__name__)

CONF_LIMIAR = config.conf_limiar
JITTER_SECONDS = config.event_jitter_seconds

_DEDUP_CACHE: Dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=2048))
_BUFFER: Dict[str, list] = defaultdict(list)
_COUNTER = itertools.count()


@dataclass
class FiltroResultado:
    prontos: List[dict]
    descartado: bool = False
    motivo: str | None = None
    buffered: bool = False


def _normalizar_timestamp(valor: Any) -> tuple[datetime, str]:
    if valor is None:
        raise ValueError("timestamp ausente")
    if isinstance(valor, datetime):
        dt = valor
    else:
        texto = str(valor).strip()
        if not texto:
            raise ValueError("timestamp invalido")
        if texto.endswith("Z"):
            texto = texto[:-1] + "+00:00"
        dt = datetime.fromisoformat(texto)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    dt = dt.replace(microsecond=0)
    return dt, dt.strftime("%Y-%m-%dT%H:%M:%S")


def _dedup_key(device_id: str, postura: str, ts_iso: str) -> str:
    return f"{device_id}:{postura}:{ts_iso}"


def filtrar(evento: Mapping[str, Any]) -> FiltroResultado:
    device_id = str(evento.get("device_id") or "").strip()
    paciente_id = str(evento.get("paciente_id") or "").strip()
    postura = str(evento.get("postura") or "").strip()
    if not device_id or not paciente_id or not postura:
        logger.warning("evento_invalido", motivo="campos_obrigatorios", evento=dict(evento))
        return FiltroResultado([], descartado=True, motivo="campos_obrigatorios")

    confianca = float(evento.get("confianca", 1.0))
    if confianca < CONF_LIMIAR:
        logger.info(
            "evento_confianca_baixa",
            device_id=device_id,
            paciente_id=paciente_id,
            confianca=confianca,
            limiar=CONF_LIMIAR,
        )
        return FiltroResultado([], descartado=True, motivo="confianca_baixa")

    try:
        ts_dt, ts_iso = _normalizar_timestamp(evento.get("ts_utc"))
    except ValueError as exc:
        logger.warning("evento_timestamp_invalido", device_id=device_id, paciente_id=paciente_id, motivo=str(exc))
        return FiltroResultado([], descartado=True, motivo="timestamp_invalido")

    chave = _dedup_key(device_id, postura, ts_iso)
    cache = _DEDUP_CACHE[device_id]
    if chave in cache:
        logger.info("evento_duplicado_descartado", device_id=device_id, paciente_id=paciente_id, ts=ts_iso)
        return FiltroResultado([], descartado=True, motivo="duplicado")
    cache.append(chave)

    evento_norm = dict(evento)
    evento_norm["ts_utc"] = ts_iso

    heap = _BUFFER[device_id]
    heapq.heappush(heap, (ts_dt, next(_COUNTER), evento_norm))

    liberar_ate = ts_dt if JITTER_SECONDS <= 0 else ts_dt - timedelta(seconds=JITTER_SECONDS)

    prontos: List[dict] = []
    while heap and heap[0][0] <= liberar_ate:
        _, _, evt = heapq.heappop(heap)
        prontos.append(evt)

    if not prontos:
        if len(heap) == 1:
            _, _, evt = heapq.heappop(heap)
            logger.debug("evento_sem_jitter", device_id=device_id, paciente_id=paciente_id, ts=ts_iso)
            return FiltroResultado(prontos=[evt])
        logger.debug("evento_bufferizado", device_id=device_id, paciente_id=paciente_id, ts=ts_iso)
        return FiltroResultado([], descartado=False, motivo=None, buffered=True)

    if heap:
        logger.debug("buffer_restante", device_id=device_id, pendentes=len(heap))
    return FiltroResultado(prontos=prontos, buffered=bool(heap))


def flush_filtro(device_id: str | None = None) -> List[dict]:
    dispositivos: Iterable[str]
    if device_id is None:
        dispositivos = list(_BUFFER.keys())
    else:
        dispositivos = [device_id]

    prontos: List[dict] = []
    for dev in dispositivos:
        heap = _BUFFER.get(dev)
        if not heap:
            continue
        quantidade = len(heap)
        while heap:
            _, _, evt = heapq.heappop(heap)
            prontos.append(evt)
        _BUFFER.pop(dev, None)
        logger.info("eventos_flush_dispositivo", device_id=dev, quantidade=quantidade)
    prontos.sort(key=lambda evt: evt["ts_utc"])
    return prontos


def reset_filtro() -> None:
    _DEDUP_CACHE.clear()
    _BUFFER.clear()
