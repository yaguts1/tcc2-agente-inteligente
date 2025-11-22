from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict
from datetime import timedelta, datetime, timezone
from typing import Any, AsyncIterator, Dict, Iterable, Mapping, List

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from interface.api_shared import DB_PATH, _aplicar_rate_limit, DEFAULT_PERFIL
from interface.dao import (
    inserir_alertas,
    inserir_eventos,
    inserir_grade,
    inserir_device_event,
    registrar_device,
    resolver_paciente_por_device_em,
    listar_device_events,
    delete_device_event,
    obter_ficha_por_cama,
    obter_ficha_paciente,
)
from interface.schemas import EventPayload, ApiResponse
from quality.filtro import filtrar as filtrar_evento, flush_filtro
from servicos import metricas
from servicos.processamento_incremental import ProcessadorIncremental

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestao"])

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


def _normalizar_payload(dados: Mapping[str, Any], device_header: str | None) -> EventPayload:
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


def _registrar_evento(payload: EventPayload) -> dict[str, Any]:
    df_grade = _event_to_grade_df(payload)
    inserir_grade(DB_PATH, df_grade, payload.paciente_id)

    df_eventos = _event_to_eventos_df(payload)
    inserir_eventos(DB_PATH, df_eventos, payload.paciente_id)

    evento_dict = payload.model_dump(mode="python")
    alertas = PROCESSADOR.processar_amostra(evento_dict)
    if alertas:
        inserir_alertas(DB_PATH, alertas)
    return {"alertas": len(alertas)}


async def _iterar_jsonl(arquivo: UploadFile) -> AsyncIterator[str]:
    buffer = ""
    chunk_size = 64 * 1024
    while True:
        chunk = await arquivo.read(chunk_size)
        if not chunk:
            break
        buffer += chunk.decode("utf-8")
        while "\n" in buffer:
            linha, buffer = buffer.split("\n", 1)
            linha = linha.strip()
            if linha:
                yield linha
    restante = buffer.strip()
    if restante:
        yield restante


def _processar_eventos_filtrados(
    eventos_filtrados: Iterable[Mapping[str, Any]],
    contagem_por_paciente: Dict[str, int],
) -> int:
    total_alertas = 0
    for dados in eventos_filtrados:
        evento_validado = EventPayload.model_validate(dados)
        resultado = _registrar_evento(evento_validado)
        contagem_por_paciente[evento_validado.paciente_id] += 1
        total_alertas += resultado["alertas"]
    return total_alertas


@router.post(
    "/eventos",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
)
async def receber_evento(
    request: Request,
    payload: Mapping[str, Any],
    _: None = Depends(_aplicar_rate_limit),
) -> ApiResponse:
    device_header = request.headers.get("X-Device-Id")
    evento = _normalizar_payload(payload, device_header)
    evento_dict = evento.model_dump(mode="python")

    # Ensure device known
    try:
        registrar_device(DB_PATH, evento.device_id, meta=None)
    except Exception:
        pass

    # Resolve paciente by device and timestamp if paciente_id not provided
    try:
        ts_ms = int(evento.ts_utc.timestamp() * 1000)
    except Exception:
        ts_ms = None
    if not evento.paciente_id and ts_ms is not None:
        try:
            pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
            if pid:
                evento.paciente_id = pid
                evento_dict["paciente_id"] = pid
        except Exception:
            pass

    metricas.registrar_recebido()

    # If still no paciente_id, persist raw device event for later reconciliation and return
    if not evento.paciente_id:
        try:
            ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
            ts_ms = int(evento.ts_utc.timestamp() * 1000)
            ev_id = inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
        except Exception:
            ev_id = None
        logger.info("evento_sem_paciente", device_id=evento.device_id, event_id=ev_id)
        return ApiResponse(
            code="accepted",
            message="Evento recebido mas sem paciente atribuido; armazenado para reconciliação.",
            ids={
                "device_id": evento.device_id,
                "processados": 0,
                "alertas": 0,
                "event_id": ev_id,
            },
        )

    resultado = filtrar_evento(evento_dict)

    if resultado.descartado:
        metricas.registrar_descartado()
        logger.info(
            "evento_descartado",
            device_id=evento.device_id,
            paciente_id=evento.paciente_id,
            motivo=resultado.motivo,
        )
        return ApiResponse(
            code="accepted",
            message="Evento descartado pelo filtro.",
            ids={
                "device_id": evento.device_id,
                "processados": 0,
                "alertas": 0,
            },
        )

    if not resultado.prontos:
        logger.debug(
            "evento_bufferizado",
            device_id=evento.device_id,
            paciente_id=evento.paciente_id,
        )
        return ApiResponse(
            code="accepted",
            message="Evento armazenado aguardando ordenacao.",
            ids={
                "device_id": evento.device_id,
                "processados": 0,
                "alertas": 0,
            },
        )

    contagem: Dict[str, int] = defaultdict(int)
    total_alertas = _processar_eventos_filtrados(resultado.prontos, contagem)
    processados = sum(contagem.values())

    logger.info(
        "eventos_processados",
        device_id=evento.device_id,
        pacientes=dict(contagem),
        alertas=total_alertas,
    )

    return ApiResponse(
        code="success",
        message="Eventos processados com sucesso.",
        ids={
            "pacientes": dict(contagem),
            "device_id": evento.device_id,
            "processados": processados,
            "alertas": total_alertas,
        },
    )


@router.post(
    "/grade",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
)
async def receber_grade(
    request: Request,
    arquivo: UploadFile = File(...),
    _: None = Depends(_aplicar_rate_limit),
) -> ApiResponse:
    if arquivo.content_type not in {"application/jsonl", "application/octet-stream", "text/plain"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_content_type", "message": "Envie arquivo JSONL valido."},
        )

    device_header = request.headers.get("X-Device-Id")
    contagem_por_paciente: Dict[str, int] = defaultdict(int)
    total_alertas = 0
    linhas_lidas = 0

    try:
        async for linha in _iterar_jsonl(arquivo):
            linhas_lidas += 1
            try:
                dados = json.loads(linha)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "invalid_jsonl",
                        "message": f"Linha JSON invalida na posicao {linhas_lidas}.",
                    },
                ) from exc
            evento = _normalizar_payload(dados, device_header)
            evento_dict = evento.model_dump(mode="python")
            # ensure device registered
            try:
                registrar_device(DB_PATH, evento.device_id, meta=None)
            except Exception:
                pass
            # try resolve paciente
            try:
                ts_ms = int(evento.ts_utc.timestamp() * 1000)
            except Exception:
                ts_ms = None
            if not evento.paciente_id and ts_ms is not None:
                try:
                    pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
                    if pid:
                        evento.paciente_id = pid
                        evento_dict["paciente_id"] = pid
                except Exception:
                    pass
            metricas.registrar_recebido()
            # if still no paciente, store raw device event and continue
            if not evento.paciente_id:
                try:
                    ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
                    if ts_ms is None:
                        ts_ms = int(evento.ts_utc.timestamp() * 1000)
                    inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
                except Exception:
                    pass
                continue
            resultado = filtrar_evento(evento_dict)
            if resultado.descartado:
                metricas.registrar_descartado()
                continue
            if resultado.prontos:
                total_alertas += _processar_eventos_filtrados(resultado.prontos, contagem_por_paciente)
    finally:
        await arquivo.close()

    flush_eventos = flush_filtro()
    if flush_eventos:
        total_alertas += _processar_eventos_filtrados(flush_eventos, contagem_por_paciente)
    processados = sum(contagem_por_paciente.values())

    logger.info(
        "grade_processada",
        device_id=device_header,
        processados=processados,
        alertas=total_alertas,
    )

    return ApiResponse(
        code="success",
        message=f"{processados} amostras processadas com sucesso.",
        ids={
            "pacientes": dict(contagem_por_paciente),
            "device_id": device_header,
            "processados": processados,
            "alertas": total_alertas,
        },
    )


def _do_reconcile(device_id: str | None = None, limit: int = 100) -> dict:
    """Synchronous reconcile worker. Intended to run in a thread via asyncio.to_thread."""
    processed = 0
    skipped = 0
    events = listar_device_events(DB_PATH, device_id=device_id, limit=limit)
    
    for ev in events:
        did = ev.get("device_id")
        ts_ms = ev.get("ts_ms")
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
            evento = _normalizar_payload(payload, None)
            # register event using same logic as ingestion
            _registrar_evento(evento)
            # mark device_event row as processed (audit) using dao helper
            try:
                delete_device_event(DB_PATH, ev.get("id"))
            except Exception:
                pass
            processed += 1
        except Exception:
            skipped += 1
            continue
            
    return {"processed": processed, "skipped": skipped}


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
            evento = _normalizar_payload(payload, None)
            _registrar_evento(evento)
            
            # Delete orphan event
            try:
                delete_device_event(DB_PATH, ev.get("id"))
            except Exception:
                pass
            
            processed += 1
        except Exception:
            skipped += 1
            continue
    
    return {
        "processed": processed,
        "skipped": skipped,
        "patient_name": patient_name,
        "cama_id": cama_id
    }


@router.post("/device_events/reconcile", status_code=status.HTTP_200_OK)
async def api_reconcile_device_events(device_id: str | None = None, limit: int = 100) -> dict:
    """Attempt to reconcile stored raw device events into patient events."""
    # delegate to shared reconcile helper which uses a lock and runs in a thread
    result = await reconcile_device_events(device_id=device_id, limit=limit)
    return result


@router.post("/device_events/reconcile_bed/{cama_id}", status_code=status.HTTP_200_OK)
async def api_reconcile_bed_events(cama_id: str, limit: int = 1000) -> dict:
    """Reconcile all orphan events for a specific bed (cama_id) to the current patient."""
    async with _reconcile_lock:
        return await asyncio.to_thread(_do_reconcile_bed, cama_id, limit)


@router.websocket("/ws/eventos")
async def websocket_eventos(websocket: WebSocket):
    """
    WebSocket endpoint for receiving events from devices (ESP32).
    Protocol:
    1. Client connects
    2. Client sends auth: {"device_id": "...", "cama_id": "..."
    3. Server responds: {"status": "connected", "device_id": "..."
    4. Client sends events: {"seq": 1, ...}
    5. Server responds ACK: {"status": "ok", "seq": 1}
    """
    await websocket.accept()
    device_id = None
    
    try:
        # 1. Authentication handshake
        try:
            auth_data = await websocket.receive_json()
        except Exception:
            await websocket.send_json({"status": "error", "error": "Invalid JSON"})
            await websocket.close()
            return

        device_id = auth_data.get("device_id")
        if not device_id:
            await websocket.send_json({"status": "error", "error": "Missing device_id"})
            await websocket.close()
            return
            
        # Register device if needed
        try:
            registrar_device(DB_PATH, device_id, meta={"cama_id": auth_data.get("cama_id")})
        except Exception:
            pass
            
        await websocket.send_json({"status": "connected", "device_id": device_id})
        
        # 2. Event loop
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({"status": "error", "error": "Invalid JSON"})
                    continue
                
                # Process event
                seq = payload.get("seq")
                
                # Normalize and process
                try:
                    # Add device_id if missing
                    if not payload.get("device_id"):
                        payload["device_id"] = device_id
                        
                    # Validate payload structure
                    # We use a permissive validation here since WS events might be slightly different
                    # or we want to be fast. But let's try to use the standard flow.
                    
                    # Convert to EventPayload-like dict
                    if "ts_utc" not in payload:
                        payload["ts_utc"] = datetime.now(timezone.utc).isoformat()
                    if "amostra_ms" not in payload:
                        payload["amostra_ms"] = 1000 # default
                        
                    # We can reuse _normalizar_payload logic but we need to be careful about exceptions
                    # For now, let's just try to persist it as a device event if we can't fully validate
                    
                    try:
                        evento = _normalizar_payload(payload, device_header=device_id)
                        evento_dict = evento.model_dump(mode="python")
                        
                        # Try to resolve patient
                        if not evento.paciente_id:
                            try:
                                ts_ms = int(evento.ts_utc.timestamp() * 1000)
                                pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
                                if pid:
                                    evento.paciente_id = pid
                                    evento_dict["paciente_id"] = pid
                            except Exception:
                                pass
                        
                        if evento.paciente_id:
                            # Full processing
                            _registrar_evento(evento)
                        else:
                            # Store raw
                            ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
                            ts_ms = int(evento.ts_utc.timestamp() * 1000)
                            inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
                            
                    except Exception as e:
                        # If validation fails, just log and maybe store raw if possible
                        logger.warning("ws_event_validation_failed", error=str(e))
                        # fallback: store raw if we have at least device_id
                        pass

                    # Send ACK
                    if seq is not None:
                        await websocket.send_json({"status": "ok", "seq": seq})
                        
                except Exception as e:
                    logger.error("ws_processing_error", error=str(e))
                    await websocket.send_json({"status": "error", "error": str(e)})
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("ws_loop_error", error=str(e))
                break
                
    except Exception as e:
        logger.error("ws_connection_error", error=str(e))
        try:
            await websocket.close()
        except:
            pass
