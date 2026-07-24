"""Logica de negocio de ingestao de eventos: normalizacao de payload,
persistencia (grade/eventos/alertas via ProcessadorIncremental) e
reconciliacao de device_events orfaos. Extraido de interface/routers/ingestao.py
para manter o router focado em parsing de request/response HTTP.
"""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from typing import Any, Dict, Iterable, Mapping

import pandas as pd
import structlog
from fastapi import HTTPException, status
from pydantic import ValidationError

from interface.api_shared import DB_PATH, DEFAULT_PERFIL
from interface.dao import obter_ficha_paciente, obter_ficha_por_cama
from interface.repositories.alertas import inserir_alertas
from interface.repositories.devices import (
    delete_device_event,
    inserir_device_event,
    listar_device_events,
    resolver_paciente_por_device_em,
)
from interface.repositories.grade import inserir_eventos, inserir_grade
from interface.schemas import EventPayload
from servicos.processamento_incremental import ProcessadorIncremental

logger = structlog.get_logger(__name__)

_reconcile_lock = asyncio.Lock()


def _resolver_perfil(paciente_id: str) -> str:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=False)
    perfil = None if ficha is None else str(ficha.get("perfil") or "").strip().lower()
    if perfil in {"baixo", "medio", "alto"}:
        return perfil
    return DEFAULT_PERFIL


PROCESSADOR = ProcessadorIncremental(
    db_path=DB_PATH,
    estrategia=os.getenv("PROCESSADOR_ESTRATEGIA", "estado_em_memoria"),
    resolver_perfil=_resolver_perfil,
)


def normalizar_payload(dados: Mapping[str, Any], device_header: str | None) -> EventPayload:
    payload_dict = dict(dados)
    if device_header and not payload_dict.get("device_id"):
        payload_dict["device_id"] = device_header
    try:
        payload = EventPayload.model_validate(payload_dict)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_payload",
                "message": "Estrutura de evento invalida.",
                "errors": exc.errors(),
            },
        ) from exc
    # If paciente_id is missing, we'll allow it for now and attempt to resolve later
    return payload


def _event_to_grade_df(payload: EventPayload) -> pd.DataFrame:
    ts_iso = payload.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
    return pd.DataFrame([{
        "timestamp": ts_iso,
        "postura": payload.postura,
        "confianca": payload.confianca
    }])


def _event_to_eventos_df(payload: EventPayload) -> pd.DataFrame:
    inicio = payload.ts_utc
    fim = inicio + timedelta(milliseconds=payload.amostra_ms)
    return pd.DataFrame(
        [
            {
                "inicio": inicio.strftime("%Y-%m-%dT%H:%M:%S"),
                "fim": fim.strftime("%Y-%m-%dT%H:%M:%S"),
                "tipo": "sensor",
            }
        ]
    )


def registrar_evento(payload: EventPayload) -> dict[str, Any]:
    df_grade = _event_to_grade_df(payload)
    inserir_grade(DB_PATH, df_grade, payload.paciente_id)

    df_eventos = _event_to_eventos_df(payload)
    inserir_eventos(DB_PATH, df_eventos, payload.paciente_id)

    evento_dict = payload.model_dump(mode="python")
    alertas = PROCESSADOR.processar_amostra(evento_dict)
    if alertas:
        inserir_alertas(DB_PATH, alertas)
    return {"alertas": len(alertas)}


def processar_eventos_filtrados(
    eventos_filtrados: Iterable[Mapping[str, Any]],
    contagem_por_paciente: Dict[str, int],
) -> int:
    total_alertas = 0
    for dados in eventos_filtrados:
        evento_validado = EventPayload.model_validate(dados)
        resultado = registrar_evento(evento_validado)
        contagem_por_paciente[evento_validado.paciente_id] += 1
        total_alertas += resultado["alertas"]
    return total_alertas


def _do_reconcile(device_id: str | None = None, limit: int = 100) -> dict:
    """Synchronous reconcile worker. Intended to run in a thread via asyncio.to_thread."""
    processed = 0
    skipped = 0
    events = listar_device_events(DB_PATH, device_id=device_id, limit=limit)

    for ev in events:
        did = ev.get("device_id")
        payload = ev.get("payload") or {}

        # Extract cama_id from payload
        cama_id = payload.get("cama_id")
        if not cama_id:
            skipped += 1
            continue

        # Find patient currently in this bed
        try:
            paciente = obter_ficha_por_cama(DB_PATH, cama_id, incluir_rotinas=False)
            pid = paciente.get("paciente_id") if paciente else None
        except Exception:
            pid = None

        if not pid:
            skipped += 1
            continue

        # attach paciente_id and try to validate/ingest
        try:
            payload["paciente_id"] = pid
            # Ensure device header present so normalization can fill missing fields
            payload["device_id"] = did
            evento = normalizar_payload(payload, None)
            # register event using same logic as ingestion
            registrar_evento(evento)
        except Exception as exc:
            logger.warning("reconcile_ingest_falhou", event_id=ev.get("id"), motivo=str(exc))
            skipped += 1
            continue

        if _marcar_processado(ev.get("id")):
            processed += 1
        else:
            skipped += 1

    return {"processed": processed, "skipped": skipped}


def _marcar_processado(event_id) -> bool:
    """Marca um device_event como processado. Retorna True se marcou.

    Se falhar (exceção ou 0 linhas), o evento continua na fila e será
    REINGERIDO no próximo ciclo de reconcile (duplicata de grade/alertas) —
    por isso registramos o problema em vez de engolir com `except: pass`, e o
    chamador não conta o evento como processado.
    """
    try:
        marcados = delete_device_event(DB_PATH, event_id)
    except Exception as exc:
        logger.warning("reconcile_marca_processado_erro", event_id=event_id, motivo=str(exc))
        return False
    if not marcados:
        logger.warning("reconcile_evento_nao_marcado", event_id=event_id)
        return False
    return True


async def reconcile_device_events(device_id: str | None = None, limit: int = 100) -> dict:
    """Async wrapper around the reconcile worker that ensures only one reconcile runs at a time."""
    async with _reconcile_lock:
        return await asyncio.to_thread(_do_reconcile, device_id, limit)


def _do_reconcile_bed(cama_id: str, limit: int = 1000) -> dict:
    """Reconcile all events from a specific bed to the current patient in that bed."""
    processed = 0
    skipped = 0
    patient_name = None

    # Find current patient in this bed
    try:
        paciente = obter_ficha_por_cama(DB_PATH, cama_id, incluir_rotinas=False)
        pid = paciente.get("paciente_id") if paciente else None
        patient_name = paciente.get("nome") if paciente else None
    except Exception:
        pid = None

    if not pid:
        return {
            "processed": 0,
            "skipped": 0,
            "error": f"No patient currently in bed {cama_id}"
        }

    # Get all orphan events
    all_events = listar_device_events(DB_PATH, device_id=None, limit=10000)

    # Filter events for this cama_id
    bed_events = []
    for ev in all_events:
        payload = ev.get("payload") or {}
        if payload.get("cama_id") == cama_id:
            bed_events.append(ev)

    # Limit if needed
    if len(bed_events) > limit:
        bed_events = bed_events[:limit]

    # Process each event
    for ev in bed_events:
        did = ev.get("device_id")
        payload = ev.get("payload") or {}

        try:
            payload["paciente_id"] = pid
            payload["device_id"] = did
            evento = normalizar_payload(payload, None)
            registrar_evento(evento)
        except Exception as exc:
            logger.warning("reconcile_bed_ingest_falhou", event_id=ev.get("id"), motivo=str(exc))
            skipped += 1
            continue

        if _marcar_processado(ev.get("id")):
            processed += 1
        else:
            skipped += 1

    return {
        "processed": processed,
        "skipped": skipped,
        "patient_name": patient_name,
        "cama_id": cama_id
    }
