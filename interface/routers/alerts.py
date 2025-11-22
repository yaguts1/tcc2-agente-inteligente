from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from interface.api_shared import DB_PATH, api_cache, _check_batch_rate_limit
from interface.dao import (
    selecionar_alertas_janela,
    obter_ficha_paciente,
    selecionar_timeline,
    alterar_status_alerta,
    inserir_timeline_event,
)
from interface.schemas import BatchAlertRequest
from interface.ws_manager_optimized import ws_manager_optimized, WebSocketFilter
from ferramentas.exportador import ExportFilters, ExportService, generate_csv_filename, generate_pdf_filename
from servicos import metricas

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["alerts"])


@router.get("/frontend/alerts", status_code=status.HTTP_200_OK)
async def frontend_alerts(
    horas: int | None = 24,
    riskLevel: str | None = None,
    status_filter: str | None = None,
    room: str | None = None,
    limit: int = 100,
    offset: int = 0
) -> list[dict]:
    """Return alerts in a shape convenient for the React frontend with optional filters.

    Query Parameters:
    - horas: int (default 24) - Time window in hours
    - riskLevel: 'high'|'medium'|'low' - Filter by risk level
    - status_filter: 'pending'|'acknowledged'|'completed' - Filter by status
    - room: str - Filter by room number (fuzzy match)
    - limit: int (default 100) - Pagination limit
    - offset: int (default 0) - Pagination offset

    Each alert contains: id, patientName, room, bed, lastRepositioning (ISO),
    nextRepositioning (ISO), riskLevel (high|medium|low), status (pending|acknowledged|completed)
    """
    # Create cache key from query parameters
    cache_key = f"alerts:{horas}:{riskLevel}:{status_filter}:{room}:{limit}:{offset}"
    
    # Try to get from cache (30 second TTL)
    cached_result = await api_cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    # Cache miss - fetch from database
    raw_alerts = selecionar_alertas_janela(DB_PATH, horas)
    results: list[dict] = []
    for a in raw_alerts:
        paciente_id = a.get("paciente_id")
        inicio = a.get("inicio")
        janela_min = int(a.get("janela_min") or 0)
        perfil = str(a.get("perfil") or "medio")
        status_raw = str(a.get("status") or "aberto")

        # build id
        aid = f"{paciente_id}__{inicio}"

        # patient name and cama
        ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=False)
        patient_name = ficha.get("nome") if ficha else paciente_id
        cama_id = (ficha.get("cama_id") if ficha else None) or ""
        # split room/bed if possible (format like '201A / Leito 1' or '201A')
        room_val = cama_id
        bed = ""
        if cama_id and "/" in cama_id:
            parts = [p.strip() for p in cama_id.split("/")]
            room_val = parts[0]
            if len(parts) > 1:
                bed = parts[1]

        # last repositioning: try timeline events
        last_ts = None
        try:
            timeline = selecionar_timeline(DB_PATH, paciente_id=paciente_id, limit=50)
            # find most recent event of interest
            for ev in sorted(timeline, key=lambda r: int(r.get("ts_ms", 0)), reverse=True):
                if ev.get("tipo") in {"alert_ack", "repositioned", "alert_close", "alert_open"}:
                    last_ts = ev.get("ts")
                    break
        except Exception:
            last_ts = None
        if last_ts is None:
            last_ts = inicio

        # next repositioning: use inicio + janela_min
        try:
            from datetime import datetime, timedelta

            next_dt = datetime.fromisoformat(inicio[:19]) + timedelta(minutes=janela_min)
            next_iso = next_dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            next_iso = inicio

        # map risk
        risk_map = {"alto": "high", "medio": "medium", "baixo": "low"}
        risk_level = risk_map.get(perfil, "medium")

        status_map = {"aberto": "pending", "reconhecido": "acknowledged", "fechado": "completed"}
        status_val = status_map.get(status_raw, "pending")

        # Apply filters
        if riskLevel and risk_level != riskLevel:
            continue
        if status_filter and status_val != status_filter:
            continue
        if room and room.lower() not in room_val.lower():
            continue

        results.append(
            {
                "id": aid,
                "patientName": patient_name,
                "room": room_val,
                "bed": bed,
                "lastRepositioning": last_ts,
                "nextRepositioning": next_iso,
                "riskLevel": risk_level,
                "status": status_val,
            }
        )
    
    # Apply pagination
    paginated_results = results[offset : offset + limit]
    
    # Cache the result for 30 seconds
    await api_cache.set(cache_key, paginated_results, ttl_seconds=30)
    
    return paginated_results


@router.post("/frontend/alerts/batch/acknowledge", status_code=status.HTTP_200_OK)
async def batch_acknowledge(payload: BatchAlertRequest, request: Request, _: None = Depends(_check_batch_rate_limit)) -> dict:
    """Acknowledge multiple alerts at once."""
    logger.info("batch_acknowledge_called", alert_ids_count=len(payload.alert_ids))
    
    processed = 0
    failed = 0
    errors: List[dict] = []
    broadcast_tasks: List = []
    
    # Process each alert in thread pool to avoid blocking
    async def _process_alert(alert_id: str) -> tuple[bool, dict]:
        try:
            paciente_id, inicio = alert_id.split("__", 1)
            # Run DB operation in thread pool
            await asyncio.to_thread(
                alterar_status_alerta, 
                DB_PATH, paciente_id, inicio, "reconhecido"
            )
            
            # Registrar evento na timeline (em thread pool também)
            try:
                await asyncio.to_thread(
                    inserir_timeline_event,
                    DB_PATH,
                    paciente_id,
                    "alert_ack",
                    f"Alerta reconhecido em lote",
                    {"alert_id": alert_id, "inicio": inicio, "action": "batch_acknowledge"}
                )
            except Exception as timeline_err:
                logger.warning(
                    "batch_ack_timeline_failed",
                    alert_id=alert_id,
                    error=str(timeline_err)
                )
            
            # Queue WebSocket broadcast as background task
            try:
                task = asyncio.create_task(ws_manager_optimized.broadcast({
                    "type": "alert_update",
                    "alert_id": alert_id,
                    "status": "acknowledged",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }))
                broadcast_tasks.append(task)
            except Exception as ws_err:
                logger.warning("batch_ack_broadcast_queued_failed", error=str(ws_err))
            
            return True, None
        except Exception as exc:
            return False, {"alert_id": alert_id, "error": str(exc)}
    
    # Run all alerts in parallel using thread pool
    tasks = [_process_alert(aid) for aid in payload.alert_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            failed += 1
            errors.append({"error": str(result)})
        elif result[0]:
            processed += 1
        else:
            failed += 1
            if result[1]:
                errors.append(result[1])
    
    # Schedule broadcasts to happen in background (don't wait)
    async def _log_broadcast_results() -> None:
        try:
            await asyncio.gather(*broadcast_tasks, return_exceptions=True)
        except Exception:
            pass
    
    try:
        asyncio.create_task(_log_broadcast_results())
    except Exception:
        pass
    
    # Invalidate alerts cache since data changed
    await api_cache.clear()
    
    # Record metrics
    metricas.registrar_batch_operation('acknowledge', processed)
    for _ in range(processed):
        metricas.registrar_alert_acknowledged()
    
    return {"ok": True, "processed": processed, "failed": failed, "errors": errors}


@router.post("/frontend/alerts/batch/complete", status_code=status.HTTP_200_OK)
async def batch_complete(payload: BatchAlertRequest, request: Request, _: None = Depends(_check_batch_rate_limit)) -> dict:
    """Complete multiple alerts at once."""
    logger.info("batch_complete_called", alert_ids_count=len(payload.alert_ids))
    
    processed = 0
    failed = 0
    errors: List[dict] = []
    broadcast_tasks: List = []
    
    # Process each alert in thread pool to avoid blocking
    async def _process_alert(alert_id: str) -> tuple[bool, dict]:
        try:
            paciente_id, inicio = alert_id.split("__", 1)
            # Run DB operation in thread pool
            await asyncio.to_thread(
                alterar_status_alerta, 
                DB_PATH, paciente_id, inicio, "fechado", True
            )
            
            # Registrar evento na timeline (em thread pool também)
            try:
                await asyncio.to_thread(
                    inserir_timeline_event,
                    DB_PATH,
                    paciente_id,
                    "alert_close",
                    f"Alerta fechado/completado em lote",
                    {"alert_id": alert_id, "inicio": inicio, "action": "batch_complete"}
                )
            except Exception as timeline_err:
                logger.warning(
                    "batch_complete_timeline_failed",
                    alert_id=alert_id,
                    error=str(timeline_err)
                )
            
            # Queue WebSocket broadcast as background task
            try:
                task = asyncio.create_task(ws_manager_optimized.broadcast({
                    "type": "alert_update",
                    "alert_id": alert_id,
                    "status": "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }))
                broadcast_tasks.append(task)
            except Exception as ws_err:
                logger.warning("batch_complete_broadcast_queued_failed", error=str(ws_err))
            
            return True, None
        except Exception as exc:
            return False, {"alert_id": alert_id, "error": str(exc)}
    
    # Run all alerts in parallel using thread pool
    tasks = [_process_alert(aid) for aid in payload.alert_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            failed += 1
            errors.append({"error": str(result)})
        elif result[0]:
            processed += 1
        else:
            failed += 1
            if result[1]:
                errors.append(result[1])
    
    # Schedule broadcasts to happen in background (don't wait)
    async def _log_broadcast_results() -> None:
        try:
            await asyncio.gather(*broadcast_tasks, return_exceptions=True)
        except Exception:
            pass
    
    try:
        asyncio.create_task(_log_broadcast_results())
    except Exception:
        pass
    
    # Invalidate alerts cache since data changed
    await api_cache.clear()
    
    # Record metrics
    metricas.registrar_batch_operation('complete', processed)
    for _ in range(processed):
        metricas.registrar_alert_completed()
    
    return {"ok": True, "processed": processed, "failed": failed, "errors": errors}


@router.post("/frontend/alerts/{alert_id}/acknowledge", status_code=status.HTTP_200_OK)
async def frontend_acknowledge(alert_id: str) -> dict:
    """Reconhece um alerta e registra evento na timeline."""
    try:
        paciente_id, inicio = alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        # Atualizar status do alerta no banco
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "reconhecido")
        
        # Registrar evento na timeline para auditoria e histórico
        try:
            inserir_timeline_event(
                db_path=DB_PATH,
                paciente_id=paciente_id,
                tipo="alert_ack",
                descricao=f"Alerta reconhecido pela equipe",
                meta={"alert_id": alert_id, "inicio": inicio, "action": "acknowledge"}
            )
            logger.info(
                "alert_acknowledged",
                paciente_id=paciente_id,
                alert_id=alert_id,
                timeline_event="alert_ack"
            )
        except Exception as e:
            logger.warning(
                "timeline_event_failed",
                paciente_id=paciente_id,
                alert_id=alert_id,
                tipo="alert_ack",
                error=str(e)
            )
        
        # Broadcast update via WebSocket
        await ws_manager_optimized.broadcast({
            "type": "alert_update",
            "alert_id": alert_id,
            "status": "acknowledged",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Alert not found"})
    return {"ok": True}

@router.post("/frontend/alerts/{alert_id}/complete", status_code=status.HTTP_200_OK)
async def frontend_complete(alert_id: str) -> dict:
    """Completa/fecha um alerta e registra evento na timeline."""
    try:
        paciente_id, inicio = alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        # Atualizar status do alerta no banco e definir data de fim
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "fechado", definir_fim=True)
        
        # Registrar evento na timeline para auditoria e histórico
        try:
            inserir_timeline_event(
                db_path=DB_PATH,
                paciente_id=paciente_id,
                tipo="alert_close",
                descricao=f"Alerta fechado/completado pela equipe",
                meta={"alert_id": alert_id, "inicio": inicio, "action": "complete"}
            )
            logger.info(
                "alert_completed",
                paciente_id=paciente_id,
                alert_id=alert_id,
                timeline_event="alert_close"
            )
        except Exception as e:
            logger.warning(
                "timeline_event_failed",
                paciente_id=paciente_id,
                alert_id=alert_id,
                tipo="alert_close",
                error=str(e)
            )
        
        # Broadcast update via WebSocket
        await ws_manager_optimized.broadcast({
            "type": "alert_update",
            "alert_id": alert_id,
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Alert not found"})
    return {"ok": True}

# ==================== EXPORT ENDPOINTS ====================

@router.get("/alerts/export/csv")
async def export_alerts_csv(
    request: Request,
    start_date: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Status: pending, acknowledged, completed"),
    patient_id: Optional[str] = Query(None, description="ID do paciente"),
    limit: int = Query(10000, ge=1, le=100000, description="Limite de registros"),
):
    """
    Exporta alertas em formato CSV.
    
    Query Parameters:
    - start_date: Data inicial no formato YYYY-MM-DD
    - end_date: Data final no formato YYYY-MM-DD
    - status: Status do alerta (pending, acknowledged, completed)
    - patient_id: ID do paciente
    - limit: Limite de registros (máximo 100000)
    
    Returns:
    - CSV file with alerts data
    """
    try:
        # Validar autenticação
        user = request.cookies.get("session_user")
        if not user:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                if ":" in token:
                    user = token.split(":")[0]
        
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Não autenticado")
        
        # Parsear datas
        start_dt = None
        end_dt = None
        
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(400, detail="start_date inválido. Use YYYY-MM-DD")
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(400, detail="end_date inválido. Use YYYY-MM-DD")
        
        # Criar filtros
        filters = ExportFilters(
            start_date=start_dt,
            end_date=end_dt,
            status=status_filter,
            patient_id=patient_id,
            limit=limit,
        )
        
        # Validar filtros
        valid, error = filters.validate()
        if not valid:
            raise HTTPException(400, detail=error)
        
        # Gerar CSV
        export_service = ExportService(DB_PATH)
        csv_content = export_service.export_to_csv(filters, username=user)
        
        # Gerar nome do arquivo
        filename = generate_csv_filename(filters)
        
        # Retornar como arquivo
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("csv_export_error", error=str(e), user=user if "user" in locals() else None)
        raise HTTPException(500, detail=f"Erro ao exportar CSV: {str(e)}")


@router.get("/alerts/export/pdf")
async def export_alerts_pdf(
    request: Request,
    start_date: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Status: pending, acknowledged, completed"),
    patient_id: Optional[str] = Query(None, description="ID do paciente"),
):
    """
    Exporta alertas em formato PDF.
    
    Query Parameters:
    - start_date: Data inicial no formato YYYY-MM-DD
    - end_date: Data final no formato YYYY-MM-DD
    - status: Status do alerta (pending, acknowledged, completed)
    - patient_id: ID do paciente
    
    Returns:
    - PDF file with formatted alerts report
    """
    try:
        # Validar autenticação
        user = request.cookies.get("session_user")
        if not user:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                if ":" in token:
                    user = token.split(":")[0]
        
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Não autenticado")
        
        # Parsear datas
        start_dt = None
        end_dt = None
        
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(400, detail="start_date inválido. Use YYYY-MM-DD")
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(400, detail="end_date inválido. Use YYYY-MM-DD")
        
        # Criar filtros
        filters = ExportFilters(
            start_date=start_dt,
            end_date=end_dt,
            status=status_filter,
            patient_id=patient_id,
            limit=10000,
        )
        
        # Validar filtros
        valid, error = filters.validate()
        if not valid:
            raise HTTPException(400, detail=error)
        
        # Gerar PDF
        export_service = ExportService(DB_PATH)
        pdf_content = export_service.export_to_pdf(filters, username=user)
        
        # Gerar nome do arquivo
        filename = generate_pdf_filename(filters)
        
        # Retornar como arquivo
        return StreamingResponse(
            iter([pdf_content]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pdf_export_error", error=str(e), user=user if "user" in locals() else None)
        raise HTTPException(500, detail=f"Erro ao exportar PDF: {str(e)}")


# ==================== END EXPORT ENDPOINTS ====================


# WebSocket endpoint for real-time alerts
@router.websocket("/ws/alerts")
async def websocket_alerts(
    websocket: WebSocket,
    severity: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None),
    alert_types: Optional[str] = Query(None),
):
    """WebSocket endpoint for real-time alert updates with filtering.
    
    Connects a client to the alert broadcast stream. New alerts will be pushed
    to the client immediately when they are created/updated, filtered by the
    specified criteria.
    
    Query Parameters:
        severity: Comma-separated list of severities (e.g., "high,critical")
        patient_id: Filter by specific patient (e.g., "PAC-0001")
        alert_types: Comma-separated list of alert types (e.g., "heart_rate,pressure")
    
    Example:
        ws://localhost:8000/api/ws/alerts?severity=high,critical&patient_id=PAC-0001
    """
    # Parse filters
    severities = severity.split(",") if severity else None
    types = alert_types.split(",") if alert_types else None
    
    filters = WebSocketFilter(
        severities=severities,
        patient_id=patient_id,
        alert_types=types,
    )
    
    await ws_manager_optimized.connect(websocket, filters=filters)
    try:
        while True:
            # Keep connection alive - receive heartbeat messages from client
            data = await websocket.receive_text()
            # Optional: handle client commands (e.g., "ping", "subscribe", "unsubscribe")
            # For now, just acknowledge receipt
            if data:
                structlog.get_logger(__name__).debug("ws_received", data=data)
    except WebSocketDisconnect:
        await ws_manager_optimized.disconnect(websocket)
    except Exception as e:
        structlog.get_logger(__name__).error("ws_error", error=str(e))
        await ws_manager_optimized.disconnect(websocket)
