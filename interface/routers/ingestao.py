from __future__ import annotations

import asyncio
import json
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status, WebSocket, WebSocketDisconnect

from interface.api_shared import DB_PATH, _aplicar_rate_limit
from interface.dependencies import (
    TOKEN_DISPOSITIVO_HEADER,
    token_dispositivo_configurado,
    verificar_token_dispositivo,
)
from interface.repositories.devices import inserir_device_event, registrar_device, resolver_paciente_por_device_em
from interface.schemas import ApiResponse
from interface.services.ingestao_service import (
    PROCESSADOR,
    _do_reconcile_bed,
    _reconcile_lock,
    normalizar_payload,
    processar_eventos_filtrados,
    reconcile_device_events,
    registrar_evento,
)
from quality.filtro import filtrar as filtrar_evento, flush_filtro
from servicos import metricas

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestao"])


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


@router.post(
    "/eventos",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
)
async def receber_evento(
    request: Request,
    payload: Dict[str, Any],
    _: None = Depends(_aplicar_rate_limit),
    __: None = Depends(verificar_token_dispositivo),
) -> ApiResponse:
    device_header = request.headers.get("X-Device-Id")
    evento = normalizar_payload(payload, device_header)
    evento_dict = evento.model_dump(mode="python")

    # Ensure device known. Falha aqui é benigna: o device já pode estar
    # registrado e a amostra ainda pode ser processada — mas precisa ser vista.
    try:
        registrar_device(DB_PATH, evento.device_id, meta=None)
    except Exception:
        logger.warning("registrar_device_falhou", device_id=evento.device_id, exc_info=True)

    # Resolve paciente by device and timestamp if paciente_id not provided
    try:
        ts_ms = int(evento.ts_utc.timestamp() * 1000)
    except Exception:
        ts_ms = None
    if not evento.paciente_id and ts_ms is not None:
        # Falha na resolução é benigna: cai no caminho de evento órfão abaixo,
        # que persiste a amostra para reconciliação posterior.
        try:
            pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
            if pid:
                evento.paciente_id = pid
                evento_dict["paciente_id"] = pid
        except Exception:
            logger.warning(
                "resolver_paciente_falhou", device_id=evento.device_id, ts_ms=ts_ms, exc_info=True
            )

    metricas.registrar_recebido()

    # If still no paciente_id, persist raw device event for later reconciliation and return
    if not evento.paciente_id:
        # Este é o ÚNICO lugar onde a amostra é guardada. Se falhar, o dado do
        # sensor está perdido — não pode responder "accepted".
        try:
            ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
            ts_ms = int(evento.ts_utc.timestamp() * 1000)
            ev_id = inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
        except Exception as exc:
            logger.exception("evento_orfao_nao_persistido", device_id=evento.device_id)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "persistencia_indisponivel",
                    "message": "Falha ao armazenar o evento; reenvie.",
                },
            ) from exc
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
    total_alertas = processar_eventos_filtrados(resultado.prontos, contagem)
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
    __: None = Depends(verificar_token_dispositivo),
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
    perdidos = 0  # amostras que nao puderam ser persistidas

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
            evento = normalizar_payload(dados, device_header)
            evento_dict = evento.model_dump(mode="python")
            # ensure device registered (falha benigna: device já pode existir)
            try:
                registrar_device(DB_PATH, evento.device_id, meta=None)
            except Exception:
                logger.warning("registrar_device_falhou", device_id=evento.device_id, exc_info=True)
            # try resolve paciente
            try:
                ts_ms = int(evento.ts_utc.timestamp() * 1000)
            except Exception:
                ts_ms = None
            if not evento.paciente_id and ts_ms is not None:
                # Falha benigna: cai no caminho de órfão, que persiste a amostra.
                try:
                    pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
                    if pid:
                        evento.paciente_id = pid
                        evento_dict["paciente_id"] = pid
                except Exception:
                    logger.warning(
                        "resolver_paciente_falhou", device_id=evento.device_id, ts_ms=ts_ms, exc_info=True
                    )
            metricas.registrar_recebido()
            # if still no paciente, store raw device event and continue
            if not evento.paciente_id:
                # Perder isto significa perder a amostra. Não aborta o lote
                # inteiro por uma linha, mas contabiliza e reporta na resposta.
                try:
                    ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
                    if ts_ms is None:
                        ts_ms = int(evento.ts_utc.timestamp() * 1000)
                    inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
                except Exception:
                    perdidos += 1
                    logger.exception(
                        "evento_orfao_nao_persistido",
                        device_id=evento.device_id,
                        linha=linhas_lidas,
                    )
                continue
            resultado = filtrar_evento(evento_dict)
            if resultado.descartado:
                metricas.registrar_descartado()
                continue
            if resultado.prontos:
                total_alertas += processar_eventos_filtrados(resultado.prontos, contagem_por_paciente)
    finally:
        await arquivo.close()

    flush_eventos = flush_filtro()
    if flush_eventos:
        total_alertas += processar_eventos_filtrados(flush_eventos, contagem_por_paciente)
    processados = sum(contagem_por_paciente.values())

    logger.info(
        "grade_processada",
        device_id=device_header,
        processados=processados,
        alertas=total_alertas,
        perdidos=perdidos,
    )

    if perdidos:
        mensagem = (
            f"{processados} amostras processadas; {perdidos} nao puderam ser "
            "armazenadas e devem ser reenviadas."
        )
    else:
        mensagem = f"{processados} amostras processadas com sucesso."

    return ApiResponse(
        code="partial" if perdidos else "success",
        message=mensagem,
        ids={
            "pacientes": dict(contagem_por_paciente),
            "device_id": device_header,
            "processados": processados,
            "alertas": total_alertas,
            "perdidos": perdidos,
        },
    )


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
    2. Client sends auth: {"device_id": "...", "cama_id": "...", "token": "..."}
    3. Server responds: {"status": "connected", "device_id": "..."
    4. Client sends events: {"seq": 1, ...}
    5. Server responds ACK: {"status": "ok", "seq": 1}

    O token pode vir no header X-Device-Token (handshake HTTP) ou no campo
    `token` da mensagem de auth — o segundo caminho existe porque nem toda
    biblioteca de WebSocket em firmware permite definir headers.
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

        esperado = token_dispositivo_configurado()
        if esperado:
            recebido = websocket.headers.get(TOKEN_DISPOSITIVO_HEADER) or auth_data.get("token") or ""
            if not secrets.compare_digest(recebido, esperado):
                logger.warning("ws_device_token_invalido", device_id=device_id)
                await websocket.send_json({"status": "error", "error": "invalid_device_token"})
                await websocket.close()
                return

        # Register device if needed (falha benigna: device já pode existir)
        try:
            registrar_device(DB_PATH, device_id, meta={"cama_id": auth_data.get("cama_id")})
        except Exception:
            logger.warning("registrar_device_falhou", device_id=device_id, exc_info=True)

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
                        payload["amostra_ms"] = 1000  # default

                    # We can reuse normalizar_payload logic but we need to be careful about exceptions
                    # For now, let's just try to persist it as a device event if we can't fully validate

                    persistido = False
                    try:
                        evento = normalizar_payload(payload, device_header=device_id)
                        evento_dict = evento.model_dump(mode="python")

                        # Try to resolve patient (falha benigna: cai no raw abaixo)
                        if not evento.paciente_id:
                            try:
                                ts_ms = int(evento.ts_utc.timestamp() * 1000)
                                pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
                                if pid:
                                    evento.paciente_id = pid
                                    evento_dict["paciente_id"] = pid
                            except Exception:
                                logger.warning(
                                    "resolver_paciente_falhou", device_id=evento.device_id, exc_info=True
                                )

                        if evento.paciente_id:
                            # Full processing
                            registrar_evento(evento)
                        else:
                            # Store raw
                            ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
                            ts_ms = int(evento.ts_utc.timestamp() * 1000)
                            inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
                        persistido = True

                    except Exception as e:
                        # Validação falhou. O fallback abaixo era prometido num
                        # comentário mas nunca existiu: o evento era descartado e
                        # mesmo assim recebia ACK "ok", então o device o dava por
                        # entregue e a amostra sumia.
                        logger.warning("ws_event_validation_failed", error=str(e))
                        try:
                            ts_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                            ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                            inserir_device_event(DB_PATH, device_id, ts_iso, ts_ms, payload)
                            persistido = True
                        except Exception:
                            logger.exception("ws_event_nao_persistido", device_id=device_id)

                    # ACK só quando a amostra está realmente guardada; caso
                    # contrário o device precisa saber para reenviar.
                    if seq is not None:
                        if persistido:
                            await websocket.send_json({"status": "ok", "seq": seq})
                        else:
                            await websocket.send_json(
                                {"status": "error", "seq": seq, "error": "persist_failed"}
                            )

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
        except Exception:
            pass
