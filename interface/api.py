"""Endpoints de ingesto de eventos e grades para processamento incremental."""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Iterable, List, Mapping

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from passlib.hash import bcrypt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from interface.dao import (
    inserir_alertas,
    inserir_eventos,
    inserir_grade,
    obter_ficha_paciente,
    listar_fichas_pacientes,
    obter_ficha_por_cama,
    selecionar_timeline,
    selecionar_alertas_janela,
    inserir_timeline_event,
    registrar_device,
    listar_devices,
    resolver_paciente_por_device_em,
    inserir_device_event,
    listar_device_assignments,
    start_device_assignment,
    end_device_assignment,
    listar_device_events,
    delete_device_event,
    alterar_status_alerta,
    criar_usuario,
    obter_usuario_por_nome,
)
from quality.filtro import FiltroResultado, filtrar as filtrar_evento, flush_filtro, reset_filtro
from servicos import metricas
from servicos.processamento_incremental import ProcessadorIncremental

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")
DEFAULT_PERFIL = "medio"

router = APIRouter(prefix="/api", tags=["api"])


# Simple session-based auth for the SPA.
@router.post("/auth/login", status_code=status.HTTP_200_OK)
async def api_login(request: Request) -> dict:
    body = await request.json()
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not username or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_request"})

    # Try to fetch user from DB
    user = None
    try:
        user = obter_usuario_por_nome(DB_PATH, username)
    except Exception:
        user = None

    # If we have a DB user, verify hashed password
    if user is not None and user.get("password_hash"):
        ph = user.get("password_hash")
        try:
            ok = bcrypt.verify(password, ph)
        except Exception:
            ok = False
        if not ok:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_credentials", "message": "Usuario ou senha invalidos"})
    else:
        # fallback to legacy env var password for quick dev (keeps backward compatibility)
        admin_pass = os.getenv("UPP_ADMIN_PASS", "admin")
        if password != admin_pass:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_credentials", "message": "Usuario ou senha invalidos"})

    # set cookie for session (simple)
    resp = {"username": username}
    from fastapi import Response

    response = Response(content=json.dumps(resp), media_type="application/json", status_code=status.HTTP_200_OK)
    # cookie lasts for 8 hours
    response.set_cookie("session_user", username, max_age=8 * 3600, httponly=True)
    return response


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def api_register(req: RegisterRequest) -> dict:
    username = str(req.username or "").strip()
    password = str(req.password or "")
    display = None if req.display_name is None else str(req.display_name).strip() or None
    if not username or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_request", "message": "username e password necessarios"})

    # hash password
    try:
        password_hash = bcrypt.hash(password)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "hash_error", "message": str(exc)})

    try:
        criar_usuario(DB_PATH, username, password_hash, display)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "user_exists", "message": str(exc)})
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "db_error", "message": str(exc)})

    # auto-login after register: set cookie
    from fastapi import Response

    resp = {"username": username}
    response = Response(content=json.dumps(resp), media_type="application/json", status_code=status.HTTP_201_CREATED)
    response.set_cookie("session_user", username, max_age=8 * 3600, httponly=True)
    return response


@router.post("/auth/logout", status_code=status.HTTP_200_OK)
async def api_logout() -> dict:
    from fastapi import Response

    response = Response(content=json.dumps({"ok": True}), media_type="application/json", status_code=status.HTTP_200_OK)
    response.delete_cookie("session_user")
    return response


@router.get("/auth/me", status_code=status.HTTP_200_OK)
async def api_me(request: Request) -> dict:
    user = request.cookies.get("session_user")
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "not_authenticated"})
    return {"username": user}

_TOKEN_BUCKET_CAPACITY = 30.0
_TOKEN_BUCKET_REFILL_RATE = 10.0  # tokens por segundo
_rate_limiter_lock = asyncio.Lock()
_rate_buckets: Dict[str, Dict[str, float]] = {}
_reconcile_lock = asyncio.Lock()


class EventPayload(BaseModel):
    """Modelo de evento recebido pelos endpoints."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1, max_length=64)
    paciente_id: str | None = Field(None)
    cama_id: str | None = Field(None)
    postura: str = Field(..., min_length=1, max_length=64)
    confianca: float = Field(..., ge=0.0, le=1.0)
    amostra_ms: int = Field(..., gt=0)
    ts_utc: datetime
    pressao_pico: float | None = Field(default=None)

    @field_validator("ts_utc")
    @classmethod
    def _normalizar_ts(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=0)


class RotinaConfig(BaseModel):
    label: str
    inicio: str
    duracao_min: int
    descricao: str | None = None
    ativo: bool
    sort_order: int


class PacienteConfigResponse(BaseModel):
    paciente_id: str
    nome: str | None = None
    cama_id: str
    perfil: str
    observacoes: str | None = None
    updated_at: str | None = None
    rotinas: List[RotinaConfig]


class ApiResponse(BaseModel):
    code: str
    message: str
    ids: dict[str, Any]


class DeviceRegisterRequest(BaseModel):
    device_id: str
    meta: dict | None = None


class AssignmentRequest(BaseModel):
    cama_id: str | None = None
    paciente_id: str | None = None
    start_ts: str | None = None
    start_ms: int | None = None



def _resolver_perfil(paciente_id: str) -> str:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=False)
    perfil = None if ficha is None else str(ficha.get("perfil") or "").strip().lower()
    if perfil in {"baixo", "medio", "alto"}:
        return perfil
    return DEFAULT_PERFIL


logger = structlog.get_logger(__name__)

PROCESSADOR = ProcessadorIncremental(
    db_path=DB_PATH,
    estrategia=os.getenv("PROCESSADOR_ESTRATEGIA", "estado_em_memoria"),
    resolver_perfil=_resolver_perfil,
)


@router.get(
    "/pacientes/cama/{cama_id}",
    response_model=PacienteConfigResponse,
    status_code=status.HTTP_200_OK,
)
async def obter_paciente_por_cama_endpoint(cama_id: str) -> PacienteConfigResponse:
    ficha = obter_ficha_por_cama(DB_PATH, cama_id, incluir_rotinas=True)
    if ficha is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "paciente_nao_encontrado",
                "message": "Nenhum paciente vinculado a esta cama.",
            },
        )
    rotinas_payload: List[RotinaConfig] = []
    for idx, rotina in enumerate(ficha.get("rotinas") or []):
        try:
            duracao_val = int(rotina.get("duracao_min", 0) or 0)
        except (TypeError, ValueError):
            duracao_val = 0
        try:
            sort_val = int(rotina.get("sort_order", idx))
        except (TypeError, ValueError):
            sort_val = idx
        rotinas_payload.append(
            RotinaConfig(
                label=str(rotina.get("label", "")),
                inicio=str(rotina.get("inicio", "")),
                duracao_min=duracao_val,
                descricao=rotina.get("descricao"),
                ativo=bool(rotina.get("ativo", True)),
                sort_order=sort_val,
            )
        )
    return PacienteConfigResponse(
        paciente_id=str(ficha.get("paciente_id", "")),
        nome=ficha.get("nome"),
        cama_id=str(ficha.get("cama_id") or ""),
        perfil=str(ficha.get("perfil") or DEFAULT_PERFIL),
        observacoes=ficha.get("observacoes"),
        updated_at=ficha.get("updated_at"),
        rotinas=rotinas_payload,
    )


@router.post("/devices/register", status_code=status.HTTP_201_CREATED)
async def api_register_device(payload: DeviceRegisterRequest) -> dict:
    try:
        registrar_device(DB_PATH, payload.device_id, payload.meta)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "device_error", "message": str(exc)}) from exc
    return {"device_id": payload.device_id}


@router.get("/devices", status_code=status.HTTP_200_OK)
async def api_list_devices() -> list[dict]:
    return listar_devices(DB_PATH)


@router.post("/devices/{device_id}/assign", status_code=status.HTTP_201_CREATED)
async def api_start_assignment(device_id: str, body: AssignmentRequest) -> dict:
    try:
        aid = start_device_assignment(DB_PATH, device_id, cama_id=body.cama_id, paciente_id=body.paciente_id, start_ts=body.start_ts, start_ms=body.start_ms)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "assignment_error", "message": str(exc)}) from exc
    return {"assignment_id": aid}


@router.post("/devices/{device_id}/assign/end", status_code=status.HTTP_200_OK)
async def api_end_assignment(device_id: str, body: AssignmentRequest | None = None) -> dict:
    try:
        rows = end_device_assignment(DB_PATH, device_id, end_ts=(body.start_ts if body else None), end_ms=(body.start_ms if body else None))
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "assignment_error", "message": str(exc)}) from exc
    return {"ended": rows}


@router.get("/device_assignments", status_code=status.HTTP_200_OK)
async def api_list_assignments(device_id: str | None = None, limit: int = 100) -> list[dict]:
    return listar_device_assignments(DB_PATH, device_id=device_id, limit=limit)


@router.get("/device_events", status_code=status.HTTP_200_OK)
async def api_list_device_events(device_id: str | None = None, limit: int = 100) -> list[dict]:
    return listar_device_events(DB_PATH, device_id=device_id, limit=limit)

@router.get("/frontend/alerts", status_code=status.HTTP_200_OK)
async def frontend_alerts(horas: int | None = 24) -> list[dict]:
    """Return alerts in a shape convenient for the React frontend.

    Each alert contains: id, patientName, room, bed, lastRepositioning (ISO),
    nextRepositioning (ISO), riskLevel (high|medium|low), status (pending|acknowledged|completed)
    """
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
        room = cama_id
        bed = ""
        if cama_id and "/" in cama_id:
            parts = [p.strip() for p in cama_id.split("/")]
            room = parts[0]
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

        results.append(
            {
                "id": aid,
                "patientName": patient_name,
                "room": room,
                "bed": bed,
                "lastRepositioning": last_ts,
                "nextRepositioning": next_iso,
                "riskLevel": risk_level,
                "status": status_val,
            }
        )
    return results

@router.post("/frontend/alerts/{alert_id}/acknowledge", status_code=status.HTTP_200_OK)
async def frontend_acknowledge(alert_id: str) -> dict:
    try:
        paciente_id, inicio = alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "reconhecido")
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Alert not found"})
    return {"ok": True}

@router.post("/frontend/alerts/{alert_id}/complete", status_code=status.HTTP_200_OK)
async def frontend_complete(alert_id: str) -> dict:
    try:
        paciente_id, inicio = alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "fechado", definir_fim=True)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Alert not found"})
    return {"ok": True}


@router.post("/device_events/reconcile", status_code=status.HTTP_200_OK)
async def api_reconcile_device_events(device_id: str | None = None, limit: int = 100) -> dict:
    """Attempt to reconcile stored raw device events into patient events.

    For each device_event (optionally filtered by device_id), try to resolve the patient
    using `resolver_paciente_por_device_em`. If a patient is found, re-inject the payload
    into the normal processing pipeline and remove the raw device_event entry.
    Returns summary of processed and skipped events.
    """
    # delegate to shared reconcile helper which uses a lock and runs in a thread
    result = await reconcile_device_events(device_id=device_id, limit=limit)
    return result


def _do_reconcile(device_id: str | None = None, limit: int = 100) -> dict:
    """Synchronous reconcile worker. Intended to run in a thread via asyncio.to_thread.

    Returns a dict with keys 'processed' and 'skipped'.
    """
    processed = 0
    skipped = 0
    events = listar_device_events(DB_PATH, device_id=device_id, limit=limit)
    for ev in events:
        did = ev.get("device_id")
        ts_ms = ev.get("ts_ms")
        payload = ev.get("payload") or {}
        try:
            pid = resolver_paciente_por_device_em(DB_PATH, did, int(ts_ms)) if ts_ms is not None else None
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
    """Async wrapper around the reconcile worker that ensures only one reconcile runs at a time.

    Uses an asyncio.Lock and runs the blocking worker in a thread.
    """
    async with _reconcile_lock:
        return await asyncio.to_thread(_do_reconcile, device_id, limit)


async def _aplicar_rate_limit(request: Request) -> None:
    chave = request.headers.get("X-Device-Id") or (request.client.host if request.client else "anonimo")
    agora = time.monotonic()
    async with _rate_limiter_lock:
        bucket = _rate_buckets.get(chave)
        if bucket is None:
            bucket = {"tokens": _TOKEN_BUCKET_CAPACITY, "ultimo": agora}
        else:
            intervalo = max(0.0, agora - bucket["ultimo"])
            bucket["tokens"] = min(
                _TOKEN_BUCKET_CAPACITY,
                bucket["tokens"] + intervalo * _TOKEN_BUCKET_REFILL_RATE,
            )
            bucket["ultimo"] = agora
        if bucket["tokens"] < 1.0:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Quota de requisicoes excedida para este dispositivo.",
                },
            )
        bucket["tokens"] -= 1.0
        _rate_buckets[chave] = bucket
    request.state.rate_key = chave


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
    return pd.DataFrame([{"timestamp": ts_iso, "postura": payload.postura}])


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


def reset_rate_limiter() -> None:
    """Limpa o estado do rate limiter (uso em testes)."""
    _rate_buckets.clear()


def reset_processador() -> None:
    """Limpa estados incrementais, filtros e metricas (uso em testes)."""
    PROCESSADOR.reset()
    reset_filtro()


@router.get("/timeline", status_code=status.HTTP_200_OK)
async def timeline_endpoint(
    paciente_id: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Retorna eventos da timeline. Campos retornados incluem `ts` (ISO) e `ts_ms` (epoch ms).

    Filtros opcionais: paciente_id, start_ms, end_ms (todos inclusive).
    """
    if limit is None or limit <= 0:
        limit = 1000
    events = selecionar_timeline(DB_PATH, paciente_id=paciente_id, start_ms=start_ms, end_ms=end_ms, limit=limit)
    return events


class TimelineRecord(BaseModel):
    paciente_id: str | None = None
    ts_ms: int
    tipo: str
    descricao: str | None = None
    meta: dict | None = None


@router.post("/timeline/record", status_code=status.HTTP_201_CREATED)
async def timeline_record(record: TimelineRecord) -> dict:
    """Registra um evento de timeline enviado pelo cliente (ex: manual seek).

    Corpo esperado: { "paciente_id": "P1", "ts_ms": 1698331954000, "tipo": "manual_seek", ... }
    """
    # Normalize ts and ts_ms
    try:
        ts_ms = int(record.ts_ms)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_ts_ms", "message": "ts_ms invalido."}) from exc
    ts_iso = datetime.fromtimestamp(ts_ms / 1000.0).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        inserted = inserir_timeline_event(DB_PATH, record.paciente_id, ts_iso, ts_ms, record.tipo, descricao=record.descricao, meta=record.meta)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "timeline_error", "message": str(exc)}) from exc
    return {"id": inserted}


@router.get("/pacientes", status_code=status.HTTP_200_OK)
async def api_listar_pacientes(incluir_rotinas: bool = False) -> list[dict]:
    """Retorna a lista de fichas de pacientes em JSON.

    Query params:
    - incluir_rotinas: bool (default False) para incluir as rotinas associadas.
    """
    fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=incluir_rotinas)
    return fichas
