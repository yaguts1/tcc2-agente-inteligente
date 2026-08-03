"""Filtros de qualidade para eventos recebidos dos dispositivos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import Any
from collections.abc import Iterable, Mapping

import structlog

from configuracao import config
from quality.estado import criar_estado

logger = structlog.get_logger(__name__)

CONF_LIMIAR = config.conf_limiar
JITTER_SECONDS = config.event_jitter_seconds

# Dedup e buffer de reordenacao viviam em dicionarios de modulo. Com uma replica
# a mais, o dedup vira desperdicio (a PK da grade recusa a duplicata) mas o
# BUFFER perde correcao: cada replica reordena metade das amostras contra a
# propria janela, e o buffer existe justamente para corrigir chegada fora de
# ordem. Ver `quality/estado.py`.
#
# Sem REDIS_URL o backend e o de memoria, com o comportamento identico ao
# historico — instalacao de uma instancia nao paga rede nem depende de outro
# servico.
_ESTADO = criar_estado(getattr(config, "redis_url", None))


@dataclass
class FiltroResultado:
    prontos: list[dict]
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
        dt = dt.astimezone(UTC).replace(tzinfo=None)
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
    if _ESTADO.ja_visto(device_id, chave):
        logger.info("evento_duplicado_descartado", device_id=device_id, paciente_id=paciente_id, ts=ts_iso)
        return FiltroResultado([], descartado=True, motivo="duplicado")
    _ESTADO.registrar(device_id, chave)

    evento_norm = dict(evento)
    evento_norm["ts_utc"] = ts_iso

    # A ordenacao passa a ser por epoch (float) em vez de datetime: o ZSET do
    # Redis pontua por numero, e usar a MESMA chave nos dois backends impede que
    # eles divirjam sobre o que "vem antes".
    _ESTADO.guardar(device_id, ts_dt.timestamp(), evento_norm)

    corte = ts_dt if JITTER_SECONDS <= 0 else ts_dt - timedelta(seconds=JITTER_SECONDS)
    prontos = _ESTADO.liberar_ate(device_id, corte.timestamp())

    if not prontos:
        # Unico pendente: nao ha o que reordenar, entao segurar so adicionaria
        # latencia. Preserva o comportamento historico do `len(heap) == 1`.
        if _ESTADO.pendentes(device_id) == 1:
            restantes = _ESTADO.drenar(device_id)
            logger.debug("evento_sem_jitter", device_id=device_id, paciente_id=paciente_id, ts=ts_iso)
            return FiltroResultado(prontos=restantes)
        logger.debug("evento_bufferizado", device_id=device_id, paciente_id=paciente_id, ts=ts_iso)
        return FiltroResultado([], descartado=False, motivo=None, buffered=True)

    restam = _ESTADO.pendentes(device_id)
    if restam:
        logger.debug("buffer_restante", device_id=device_id, pendentes=restam)
    return FiltroResultado(prontos=prontos, buffered=bool(restam))


def flush_filtro(device_id: str | None = None) -> list[dict]:
    dispositivos: Iterable[str]
    dispositivos = _ESTADO.dispositivos() if device_id is None else [device_id]

    prontos: list[dict] = []
    for dev in dispositivos:
        drenados = _ESTADO.drenar(dev)
        if not drenados:
            continue
        prontos.extend(drenados)
        logger.info("eventos_flush_dispositivo", device_id=dev, quantidade=len(drenados))
    prontos.sort(key=lambda evt: evt["ts_utc"])
    return prontos


def reset_filtro() -> None:
    """Esquece tudo: dedup e buffer.

    Existia so para os testes. Passou a ter uso operacional: reenviar as MESMAS
    amostras (um replay repetido, uma demonstracao) era descartado como
    duplicata — com ACK, e sem nada na tela. Antes, a unica forma de recomecar
    era reiniciar o processo.
    """
    _ESTADO.limpar()
