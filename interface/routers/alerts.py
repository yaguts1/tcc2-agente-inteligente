from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from interface.api_shared import DB_PATH, _check_batch_rate_limit
from interface.schemas import BatchAlertRequest
from interface.ws_manager_optimized import ws_manager_optimized, WebSocketFilter
from interface.dependencies import get_current_user
from interface.services.alerts_service import (
    listar_alertas_frontend_paginado,
    reconhecer_alerta,
    completar_alerta,
    processar_lote,
    parsear_data_export,
)
from interface.repositories.alertas import TransicaoInvalida
from ferramentas.exportador import ExportFilters, ExportService, generate_csv_filename, generate_pdf_filename

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["alerts"])


@router.get("/frontend/alerts", status_code=status.HTTP_200_OK)
async def frontend_alerts(
    response: Response,
    horas: int | None = 24,
    riskLevel: str | None = None,
    status_filter: str | None = None,
    room: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _: str = Depends(get_current_user),
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

    Cabecalho `X-Total-Count`: quantos alertas casam com os filtros, ANTES do
    corte por `limit`. O corpo continua sendo o array puro (o contrato que o
    frontend e os testes usam), mas sem esse numero a resposta omite em
    silencio: uma lista de 100 com `limit=100` e indistinguivel de "existem
    exatamente 100", e o dashboard filtra em memoria sobre o que recebeu — um
    paciente atrasado ficaria fora da tela sem nenhum sinal.
    """
    pagina = await listar_alertas_frontend_paginado(
        horas, riskLevel, status_filter, room, limit, offset
    )
    response.headers["X-Total-Count"] = str(pagina.total)
    return pagina.itens


@router.post("/frontend/alerts/batch/acknowledge", status_code=status.HTTP_200_OK)
async def batch_acknowledge(
    payload: BatchAlertRequest,
    request: Request,
    user: str = Depends(get_current_user),
    _: None = Depends(_check_batch_rate_limit)
) -> dict:
    """Acknowledge multiple alerts at once."""
    logger.info("batch_acknowledge_called", alert_ids_count=len(payload.alert_ids), user=user)
    return await processar_lote(payload.alert_ids, user, "acknowledge")


@router.post("/frontend/alerts/batch/complete", status_code=status.HTTP_200_OK)
async def batch_complete(
    payload: BatchAlertRequest,
    request: Request,
    user: str = Depends(get_current_user),
    _: None = Depends(_check_batch_rate_limit)
) -> dict:
    """Complete multiple alerts at once."""
    logger.info("batch_complete_called", alert_ids_count=len(payload.alert_ids), user=user)
    return await processar_lote(payload.alert_ids, user, "complete")


@router.post("/frontend/alerts/{alert_id}/acknowledge", status_code=status.HTTP_200_OK)
async def frontend_acknowledge(alert_id: str, user: str = Depends(get_current_user)) -> dict:
    """Reconhece um alerta e registra evento na timeline."""
    try:
        alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        await reconhecer_alerta(alert_id, user)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Alert not found"})
    except TransicaoInvalida as exc:
        # 409, e nao 400: o pedido e valido, o estado atual do alerta e que o
        # recusa. Acontece quando duas pessoas agem no mesmo alerta em telas
        # diferentes — a segunda precisa saber que nao foi ela quem registrou,
        # em vez de receber um "ok" que a faria acreditar no contrario.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "transicao_invalida", "message": str(exc)},
        ) from exc
    return {"ok": True}


@router.post("/frontend/alerts/{alert_id}/complete", status_code=status.HTTP_200_OK)
async def frontend_complete(alert_id: str, user: str = Depends(get_current_user)) -> dict:
    """Completa/fecha um alerta e registra evento na timeline."""
    try:
        alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        await completar_alerta(alert_id, user)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Alert not found"})
    except TransicaoInvalida as exc:
        # 409, e nao 400: o pedido e valido, o estado atual do alerta e que o
        # recusa. Acontece quando duas pessoas agem no mesmo alerta em telas
        # diferentes — a segunda precisa saber que nao foi ela quem registrou,
        # em vez de receber um "ok" que a faria acreditar no contrario.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "transicao_invalida", "message": str(exc)},
        ) from exc
    return {"ok": True}


# ==================== EXPORT ENDPOINTS ====================

@router.get("/alerts/export/csv")
def export_alerts_csv(
    start_date: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Status: pending, acknowledged, completed"),
    patient_id: Optional[str] = Query(None, description="ID do paciente"),
    limit: int = Query(10000, ge=1, le=100000, description="Limite de registros"),
    user: str = Depends(get_current_user),
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

    Autenticação exigida via get_current_user (JWT em Bearer ou cookie
    access_token). Exporta dados clínicos de pacientes — nunca deixar sem auth.
    """
    try:
        try:
            start_dt = parsear_data_export(start_date, "start_date")
            end_dt = parsear_data_export(end_date, "end_date")
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc))

        filters = ExportFilters(
            start_date=start_dt,
            end_date=end_dt,
            status=status_filter,
            patient_id=patient_id,
            limit=limit,
        )

        valid, error = filters.validate()
        if not valid:
            raise HTTPException(400, detail=error)

        export_service = ExportService(DB_PATH)
        csv_content = export_service.export_to_csv(filters, username=user)
        filename = generate_csv_filename(filters)

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("csv_export_error", error=str(e), user=user)
        raise HTTPException(500, detail=f"Erro ao exportar CSV: {str(e)}")


@router.get("/alerts/export/pdf")
def export_alerts_pdf(
    start_date: Optional[str] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Data final (YYYY-MM-DD)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Status: pending, acknowledged, completed"),
    patient_id: Optional[str] = Query(None, description="ID do paciente"),
    user: str = Depends(get_current_user),
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

    Autenticação exigida via get_current_user (JWT em Bearer ou cookie
    access_token). Exporta dados clínicos de pacientes — nunca deixar sem auth.
    """
    try:
        try:
            start_dt = parsear_data_export(start_date, "start_date")
            end_dt = parsear_data_export(end_date, "end_date")
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc))

        filters = ExportFilters(
            start_date=start_dt,
            end_date=end_dt,
            status=status_filter,
            patient_id=patient_id,
            limit=10000,
        )

        valid, error = filters.validate()
        if not valid:
            raise HTTPException(400, detail=error)

        export_service = ExportService(DB_PATH)
        pdf_content = export_service.export_to_pdf(filters, username=user)
        filename = generate_pdf_filename(filters)

        return StreamingResponse(
            iter([pdf_content]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("pdf_export_error", error=str(e), user=user)
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

    NAO USADO PELO FRONTEND, E DE PROPOSITO
    ---------------------------------------
    O React abre UMA conexao (frontend/src/contexts/WebSocketContext.tsx),
    compartilhada por todos os consumidores: o dashboard, que precisa de todos
    os alertas, e a tela de Historico, que recarrega a timeline a cada
    mensagem. O filtro aqui e POR CONEXAO — aplica-lo naquela conexao unica
    silenciaria os demais consumidores, entao a nao-utilizacao e a decisao
    correta, e nao um esquecimento.

    A capacidade fica porque e o que uma futura tela por paciente (ou um painel
    de leito) precisaria, e porque o custo de manter e um `if`. Quem for
    liga-la: abra uma SEGUNDA conexao para o consumidor filtrado, sem mexer na
    compartilhada.

    Cuidado ao mexer nos payloads: `_montar_payload_broadcast` e
    `_montar_payload_alerta_novo` precisam continuar carregando `severity`,
    `patient_id` e `alert_type`, porque e contra esses campos que
    `WebSocketFilter.matches()` decide. Ja houve o caso de o payload nao os
    ter, e todo cliente com filtro ficava sem receber nada.
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
                logger.debug("ws_received", data=data)
    except WebSocketDisconnect:
        await ws_manager_optimized.disconnect(websocket)
    except Exception as e:
        logger.error("ws_error", error=str(e))
        await ws_manager_optimized.disconnect(websocket)
