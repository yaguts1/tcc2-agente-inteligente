"""Endpoints de ingesto de eventos e grades para processamento incremental."""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Iterable, List, Mapping, Optional

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse
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
    listar_device_events,
    delete_device_event,
    alterar_status_alerta,
    criar_usuario,
    obter_usuario_por_nome,
    ensure_minimal_paciente_ficha,
    remover_paciente,
    criar_paciente,
    atualizar_paciente,
)
from interface.ws_manager_optimized import (
    ws_manager_optimized,
    WebSocketFilter,
)
from dados_simulados.gerador import gerar_sessao_simulada, PerfilPaciente, PERFIS_PREDEFINIDOS
from modulo_alerta.engine import processar_alertas
from quality.filtro import FiltroResultado, filtrar as filtrar_evento, flush_filtro, reset_filtro
from servicos import metricas
from servicos.processamento_incremental import ProcessadorIncremental
from servicos.backup import BackupService, scheduled_backup_task
from ferramentas.exportador import ExportService, ExportFilters, generate_csv_filename, generate_pdf_filename

DB_PATH = os.getenv("UPP_DB_PATH", "dados.db")
DEFAULT_PERFIL = "medio"
APP_VERSION = "1.0.0"
APP_START_TIME = time.time()

router = APIRouter(prefix="/api", tags=["api"])

# Enhanced rate limiting system
class RateLimiter:
    """Flexible rate limiter with configurable windows and limits."""
    
    def __init__(self):
        self._attempts: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = asyncio.Lock()
    
    async def check_limit(self, key: str, limit: int, window_seconds: int, request: Request) -> None:
        """
        Check if request exceeds rate limit.
        
        Args:
            key: Rate limit category (e.g., 'auth', 'api', 'batch')
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
            request: FastAPI request object
        """
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        async with self._lock:
            # Clean old attempts
            if client_ip in self._attempts[key]:
                self._attempts[key][client_ip] = [
                    ts for ts in self._attempts[key][client_ip] 
                    if now - ts < window_seconds
                ]
            
            # Count attempts in window
            attempts = len(self._attempts[key].get(client_ip, []))
            
            if attempts >= limit:
                retry_after = window_seconds
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "rate_limited",
                        "message": f"Muitas requisições. Tente novamente em {window_seconds}s.",
                        "retry_after": retry_after
                    },
                    headers={"Retry-After": str(retry_after)}
                )
            
            # Record new attempt
            self._attempts[key][client_ip].append(now)
    
    def reset(self, key: str | None = None) -> None:
        """Reset rate limits (for testing)."""
        if key is None:
            self._attempts.clear()
        elif key in self._attempts:
            self._attempts[key].clear()


# Global rate limiter instance
rate_limiter = RateLimiter()


def _reset_auth_rate_limits() -> None:
    """Reset auth rate limits (for testing only)."""
    rate_limiter.reset('auth')


async def _check_auth_rate_limit(request: Request) -> None:
    """Rate limiting for login/register (5 attempts per minute per IP)."""
    await rate_limiter.check_limit('auth', limit=5, window_seconds=60, request=request)


async def _check_api_rate_limit(request: Request) -> None:
    """Rate limiting for general API endpoints (100 requests per minute per IP)."""
    await rate_limiter.check_limit('api', limit=100, window_seconds=60, request=request)


async def _check_batch_rate_limit(request: Request) -> None:
    """Rate limiting for batch operations (10 requests per minute per IP)."""
    await rate_limiter.check_limit('batch', limit=10, window_seconds=60, request=request)


# Simple in-memory cache with TTL
class SimpleCache:
    """Simple in-memory cache with TTL (Time To Live)."""
    
    def __init__(self):
        self._cache: Dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        async with self._lock:
            if key not in self._cache:
                return None
            
            value, expires_at = self._cache[key]
            if time.time() > expires_at:
                del self._cache[key]
                return None
            
            return value
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 60) -> None:
        """Set cached value with TTL."""
        async with self._lock:
            expires_at = time.time() + ttl_seconds
            self._cache[key] = (value, expires_at)
    
    async def delete(self, key: str) -> None:
        """Delete cached value."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    async def clear(self) -> None:
        """Clear all cached values."""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self) -> None:
        """Remove all expired entries."""
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired_keys:
                del self._cache[k]


# Global cache instance
api_cache = SimpleCache()


@router.post("/auth/login", status_code=status.HTTP_200_OK)
async def api_login(request: Request, _: None = Depends(_check_auth_rate_limit)) -> dict:
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

    # Generate token (use username + timestamp as simple token)
    token = f"{username}:{int(time.time())}"
    
    # set cookie for session (simple)
    resp = {"username": username, "token": token, "display_name": user.get("display_name") if user else None, "role": user.get("role", "staff") if user else "staff"}
    from fastapi import Response

    response = Response(content=json.dumps(resp), media_type="application/json", status_code=status.HTTP_200_OK)
    # cookie lasts for 8 hours
    response.set_cookie("session_user", username, max_age=8 * 3600, httponly=True)
    return response


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def prometheus_metrics():
    """
    Endpoint para exportar métricas no formato Prometheus.
    Usado para scraping pelo Prometheus server.
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    
    metrics_output = generate_latest()
    return Response(content=metrics_output, media_type=CONTENT_TYPE_LATEST)


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def api_register(request: Request, req: RegisterRequest, _: None = Depends(_check_auth_rate_limit)) -> dict:
    username = str(req.username or "").strip()
    password = str(req.password or "")
    display = None if req.display_name is None else str(req.display_name).strip() or None
    if not username or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_request", "message": "username e password necessarios"})

    # hash password
    try:
        password_hash = bcrypt.hash(password)
    except Exception as exc:
        structlog.get_logger(__name__).exception("hash_error", erro=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "hash_error", "message": str(exc)})

    try:
        structlog.get_logger(__name__).info("register_attempt", username=username)
        criar_usuario(DB_PATH, username, password_hash, display)
    except ValueError as exc:
        structlog.get_logger(__name__).warning("register_failed_user_exists", username=username, motivo=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "user_exists", "message": str(exc)})
    except Exception as exc:
        structlog.get_logger(__name__).exception("register_db_error", username=username, erro=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "db_error", "message": str(exc)})

    # auto-login after register: set cookie
    from fastapi import Response
    
    # Generate token (use username + timestamp as simple token)
    token = f"{username}:{int(time.time())}"

    resp = {"username": username, "display_name": display, "token": token, "role": "staff"}
    response = Response(content=json.dumps(resp), media_type="application/json", status_code=status.HTTP_201_CREATED)
    response.set_cookie("session_user", username, max_age=8 * 3600, httponly=True)
    return response


@router.post("/auth/logout", status_code=status.HTTP_200_OK)
async def api_logout() -> dict:
    from fastapi import Response

    response = Response(content=json.dumps({"ok": True}), media_type="application/json", status_code=status.HTTP_200_OK)
    response.delete_cookie("session_user")
    return response


# Backup endpoints
backup_service = BackupService(DB_PATH)


@router.post("/admin/backup/create", status_code=status.HTTP_200_OK)
async def create_backup() -> dict:
    """Cria um backup manual do banco de dados."""
    try:
        backup_path = await asyncio.to_thread(backup_service.create_backup)
        return {"ok": True, "backup_path": backup_path}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "backup_failed", "message": str(e)}
        )


@router.get("/admin/backup/list", status_code=status.HTTP_200_OK)
async def list_backups() -> dict:
    """Lista todos os backups disponíveis."""
    backups = await asyncio.to_thread(backup_service.list_backups)
    return {"backups": backups, "count": len(backups)}


@router.post("/admin/backup/cleanup", status_code=status.HTTP_200_OK)
async def cleanup_backups(keep_days: int = 7) -> dict:
    """Remove backups mais antigos que keep_days dias."""
    try:
        removed = await asyncio.to_thread(backup_service.cleanup_old_backups, keep_days)
        return {"ok": True, "removed_count": removed}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "cleanup_failed", "message": str(e)}
        )


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict:
    """
    Comprehensive health check endpoint.
    Returns service status, database connectivity, WebSocket connections, version, and uptime.
    """
    import sqlite3
    
    uptime_seconds = time.time() - APP_START_TIME
    uptime_hours = uptime_seconds / 3600
    
    # Check database connectivity
    db_status = "unknown"
    db_error = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM alertas")
        alert_count = cursor.fetchone()[0]
        conn.close()
        db_status = "healthy"
    except Exception as e:
        db_status = "unhealthy"
        db_error = str(e)
        alert_count = None
    
    # Get WebSocket connection count
    ws_connections = len(ws_manager_optimized.active_connections)
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": APP_VERSION,
        "uptime_seconds": round(uptime_seconds, 2),
        "uptime_hours": round(uptime_hours, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "status": db_status,
            "path": DB_PATH,
            "alert_count": alert_count,
            "error": db_error
        },
        "websocket": {
            "active_connections": ws_connections
        }
    }


@router.get("/auth/me", status_code=status.HTTP_200_OK)
async def api_me(request: Request) -> dict:
    # Try to get user from cookie first (from httpOnly cookie)
    user = request.cookies.get("session_user")
    
    # If no cookie, try to get from Authorization header (Bearer token)
    if not user:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            # Token format is "username:timestamp"
            if ":" in token:
                user = token.split(":")[0]
    
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "not_authenticated"})
    
    # try to include display_name and role when available
    try:
        u = obter_usuario_por_nome(DB_PATH, user)
        display = None if u is None else u.get("display_name")
        role = "staff" if u is None else (u.get("role") or "staff")
    except Exception:
        display = None
        role = "staff"
    return {"username": user, "display_name": display, "role": role}


@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_stats() -> dict:
    """Retorna estatísticas do dashboard para o frontend.
    
    ✅ CORRIGIDO: Usa janela temporal CONSISTENTE de 24h para todas as métricas
    
    Antes: activeAlerts=7 dias, acknowledgedAlerts=7 dias, completedToday=24h
           Causava taxa de conclusão inconsistente (misturava períodos diferentes)
    
    Agora: TODAS as métricas usam 24h (últimas 24 horas)
           Taxa de conclusão = fechados_24h / (abertos_24h + reconhecidos_24h + fechados_24h)
    
    Retorna: activeAlerts, acknowledgedAlerts, completedToday, totalPatients, completionRate
    """
    try:
        # ✅ CORRIGIDO: Usar janela CONSISTENTE de 24 horas para TODAS as métricas
        # Antes: selecionar_alertas_janela(DB_PATH, horas=168)  # 1 semana - INCONSISTENTE!
        # Agora: selecionar_alertas_janela(DB_PATH, horas=24)   # 24 horas - CONSISTENTE!
        all_alerts_24h = selecionar_alertas_janela(DB_PATH, horas=24)
        
        # Contar alertas abertos (pending) nas últimas 24h
        active_alerts = len([a for a in all_alerts_24h if a.get("status") == "aberto"])
        
        # Contar alertas reconhecidos (acknowledged) nas últimas 24h
        acked_alerts = len([a for a in all_alerts_24h if a.get("status") == "reconhecido"])
        
        # Contar alertas fechados (completed) nas últimas 24h
        completed_today = len([a for a in all_alerts_24h if a.get("status") == "fechado"])
        
        # Contar pacientes totais
        fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)
        total_patients = len(fichas)
        
        # ✅ CORRIGIDO: Taxa de conclusão agora usa dados CONSISTENTES (todas 24h)
        # Fórmula: fechados / (abertos + reconhecidos + fechados) nas últimas 24h
        # Representa: % de alertas que foram completados no período de 24h
        total_relevant = active_alerts + acked_alerts + completed_today
        completion_rate = (
            (completed_today / total_relevant * 100) 
            if total_relevant > 0 else 0
        )
        
        return {
            "activeAlerts": active_alerts,
            "acknowledgedAlerts": acked_alerts,
            "completedToday": completed_today,
            "totalPatients": total_patients,
            "completionRate": round(completion_rate, 1)
        }
    except Exception as exc:
        logger.exception("stats_error", erro=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "stats_error", "message": str(exc)}
        ) from exc


@router.get("/validate-repositioning/{paciente_id}", status_code=status.HTTP_200_OK)
async def validate_repositioning_contract(paciente_id: str) -> dict:
    """Valida o contrato Backend/Frontend para repouso.
    
    Valida:
    1. Último repouso (ultimo_repouso) < Próximo repouso (proximo_repouso)
    2. Próximo repouso (proximo_repouso) > Agora (deve estar no futuro)
    3. Intervalo entre repouso é consistente com perfil
    
    Retorna: {
        "valid": bool,
        "errors": [str],
        "ultimo_repouso": ISO string,
        "proximo_repouso": ISO string,
        "intervalo_horas": float,
        "perfil": str,
        "agora": ISO string
    }
    """
    try:
        ficha = obter_ficha_paciente(DB_PATH, paciente_id)
        if ficha is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "paciente_nao_encontrado", "message": f"Paciente {paciente_id} nao encontrado."}
            )
        
        agora = datetime.now()
        errors = []
        
        # Buscar alertas (não filtra por paciente_id na DAO, então filtramos aqui)
        todos_alertas = selecionar_alertas_janela(DB_PATH, horas=24)
        alertas = [a for a in todos_alertas if a.get("paciente_id") == paciente_id]
        
        # Buscar último alerta (último repouso)
        alertas_filtrados = [a for a in alertas if a.get("status") == "fechado"]
        
        ultimo_repouso = None
        if alertas_filtrados:
            # Pega o mais recente (último fim de alerta)
            alertas_ordenados = sorted(alertas_filtrados, key=lambda x: x.get("fim", ""), reverse=True)
            último_alerta = alertas_ordenados[0]
            if último_alerta.get("fim"):
                try:
                    ultimo_repouso = datetime.fromisoformat(último_alerta.get("fim")[:19])
                except:
                    pass
        
        # Buscar próximo alerta (próximo repouso)
        alertas_abertos = [a for a in alertas if a.get("status") == "aberto"]
        proximo_repouso = None
        if alertas_abertos:
            alertas_ordenados = sorted(alertas_abertos, key=lambda x: x.get("inicio", ""))
            próximo_alerta = alertas_ordenados[0]
            if próximo_alerta.get("inicio"):
                try:
                    proximo_repouso = datetime.fromisoformat(próximo_alerta.get("inicio")[:19])
                except:
                    pass
        
        # Validar contrato
        if ultimo_repouso and proximo_repouso:
            if ultimo_repouso >= proximo_repouso:
                errors.append(f"ultimo_repouso ({ultimo_repouso.isoformat()}) >= proximo_repouso ({proximo_repouso.isoformat()})")
        
        if proximo_repouso and proximo_repouso <= agora:
            errors.append(f"proximo_repouso ({proximo_repouso.isoformat()}) <= agora ({agora.isoformat()}) - DEVE estar no FUTURO!")
        
        intervalo_horas = None
        if ultimo_repouso and proximo_repouso:
            intervalo_horas = (proximo_repouso - ultimo_repouso).total_seconds() / 3600.0
        
        perfil = ficha.get("perfil", DEFAULT_PERFIL)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "ultimo_repouso": ultimo_repouso.isoformat() if ultimo_repouso else None,
            "proximo_repouso": proximo_repouso.isoformat() if proximo_repouso else None,
            "intervalo_horas": round(intervalo_horas, 2) if intervalo_horas else None,
            "perfil": perfil,
            "agora": agora.isoformat()
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("validate_repositioning_error", erro=str(exc), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "validate_error", "message": str(exc)}
        ) from exc

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


class FrontendCreatePatient(BaseModel):
    name: str
    room: str | None = None
    bed: str | None = None
    riskLevel: str
    repositioningInterval: int | None = None


class FrontendPatient(BaseModel):
    id: str
    name: str
    room: str | None = None
    bed: str | None = None
    riskLevel: str
    repositioningInterval: int | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class DeviceRegisterRequest(BaseModel):
    device_id: str
    meta: dict | None = None


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


@router.get("/device_events", status_code=status.HTTP_200_OK)
async def api_list_device_events(device_id: str | None = None, limit: int = 100) -> list[dict]:
    return listar_device_events(DB_PATH, device_id=device_id, limit=limit)


@router.get("/device_events/stats", status_code=status.HTTP_200_OK)
async def api_device_events_stats() -> dict:
    """Return statistics about orphan device events grouped by bed (cama_id).
    
    Returns:
    {
        "total_orphans": int,
        "beds": [
            {
                "cama_id": str,
                "count": int,
                "first_event": str (ISO timestamp),
                "last_event": str (ISO timestamp),
                "current_patient": {
                    "id": str,
                    "name": str
                } | null
            }
        ]
    }
    """
    events = listar_device_events(DB_PATH, device_id=None, limit=10000)
    
    # Group by cama_id
    bed_stats: dict[str, dict] = {}
    
    for ev in events:
        payload = ev.get("payload") or {}
        cama_id = payload.get("cama_id")
        
        if not cama_id:
            continue
            
        if cama_id not in bed_stats:
            bed_stats[cama_id] = {
                "cama_id": cama_id,
                "count": 0,
                "first_event": None,
                "last_event": None,
                "events": []
            }
        
        bed_stats[cama_id]["count"] += 1
        bed_stats[cama_id]["events"].append(ev.get("ts"))
    
    # Process timestamps and find current patients
    beds_list = []
    for cama_id, stats in bed_stats.items():
        timestamps = sorted([t for t in stats["events"] if t])
        
        result = {
            "cama_id": cama_id,
            "count": stats["count"],
            "first_event": timestamps[0] if timestamps else None,
            "last_event": timestamps[-1] if timestamps else None,
            "current_patient": None
        }
        
        # Try to find current patient in this bed
        try:
            paciente = obter_ficha_por_cama(DB_PATH, cama_id, incluir_rotinas=False)
            if paciente:
                result["current_patient"] = {
                    "id": paciente.get("paciente_id"),
                    "name": paciente.get("nome")
                }
        except Exception:
            pass
        
        beds_list.append(result)
    
    # Sort by count (descending)
    beds_list.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "total_orphans": len(events),
        "beds": beds_list
    }


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


class BatchAlertRequest(BaseModel):
    """Request body for batch alert operations."""
    alert_ids: List[str]


@router.post("/frontend/alerts/batch/acknowledge", status_code=status.HTTP_200_OK)
async def batch_acknowledge(payload: BatchAlertRequest, request: Request, _: None = Depends(_check_batch_rate_limit)) -> dict:
    """Acknowledge multiple alerts at once.
    
    Request:
    {
      "alert_ids": ["paciente_id__inicio", "paciente_id2__inicio2", ...]
    }
    
    Response:
    {
      "ok": true,
      "processed": 2,
      "failed": 0,
      "errors": []
    }
    """
    logger = structlog.get_logger(__name__)
    logger.info("batch_acknowledge_called", alert_ids_count=len(payload.alert_ids))
    
    processed = 0
    failed = 0
    errors: List[dict] = []
    broadcast_tasks: List = []
    
    # Process each alert in thread pool to avoid blocking
    async def _process_alert(alert_id: str) -> tuple[bool, dict]:
        """Process a single alert and return (success, error_dict_or_none).
        
        ✅ CORRIGIDO: Agora registra evento alert_ack na timeline.
        """
        try:
            paciente_id, inicio = alert_id.split("__", 1)
            # Run DB operation in thread pool
            await asyncio.to_thread(
                alterar_status_alerta, 
                DB_PATH, paciente_id, inicio, "reconhecido"
            )
            
            # ✅ ADICIONAR: Registrar evento na timeline (em thread pool também)
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
                # Não falhar operação se timeline der erro
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
    """Complete multiple alerts at once.
    
    Request:
    {
      "alert_ids": ["paciente_id__inicio", "paciente_id2__inicio2", ...]
    }
    
    Response:
    {
      "ok": true,
      "processed": 2,
      "failed": 0,
      "errors": []
    }
    """
    logger = structlog.get_logger(__name__)
    logger.info("batch_complete_called", alert_ids_count=len(payload.alert_ids))
    
    processed = 0
    failed = 0
    errors: List[dict] = []
    broadcast_tasks: List = []
    
    # Process each alert in thread pool to avoid blocking
    async def _process_alert(alert_id: str) -> tuple[bool, dict]:
        """Process a single alert and return (success, error_dict_or_none).
        
        ✅ CORRIGIDO: Agora registra evento alert_close na timeline.
        """
        try:
            paciente_id, inicio = alert_id.split("__", 1)
            # Run DB operation in thread pool
            await asyncio.to_thread(
                alterar_status_alerta, 
                DB_PATH, paciente_id, inicio, "fechado", True
            )
            
            # ✅ ADICIONAR: Registrar evento na timeline (em thread pool também)
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
                # Não falhar operação se timeline der erro
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
    """Reconhece um alerta e registra evento na timeline.
    
    ✅ CORRIGIDO: Agora registra evento 'alert_ack' na timeline para rastreabilidade.
    """
    try:
        paciente_id, inicio = alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        # Atualizar status do alerta no banco
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "reconhecido")
        
        # ✅ ADICIONAR: Registrar evento na timeline para auditoria e histórico
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
            # Não falhar a operação se timeline der erro, mas logar
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
    """Completa/fecha um alerta e registra evento na timeline.
    
    ✅ CORRIGIDO: Agora registra evento 'alert_close' na timeline para rastreabilidade.
    """
    try:
        paciente_id, inicio = alert_id.split("__", 1)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alert_id", "message": "Invalid alert id"})
    try:
        # Atualizar status do alerta no banco e definir data de fim
        alterar_status_alerta(DB_PATH, paciente_id, inicio, "fechado", definir_fim=True)
        
        # ✅ ADICIONAR: Registrar evento na timeline para auditoria e histórico
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
            # Não falhar a operação se timeline der erro, mas logar
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


@router.post("/device_events/reconcile", status_code=status.HTTP_200_OK)
async def api_reconcile_device_events(device_id: str | None = None, limit: int = 100) -> dict:
    """Attempt to reconcile stored raw device events into patient events.

    For each device_event (optionally filtered by device_id), try to find the current patient
    in the bed (cama_id) specified in the payload. If a patient is found, re-inject the payload
    into the normal processing pipeline and remove the raw device_event entry.
    Returns summary of processed and skipped events.
    """
    # delegate to shared reconcile helper which uses a lock and runs in a thread
    result = await reconcile_device_events(device_id=device_id, limit=limit)
    return result


@router.post("/device_events/reconcile_bed/{cama_id}", status_code=status.HTTP_200_OK)
async def api_reconcile_bed_events(cama_id: str, limit: int = 1000) -> dict:
    """Reconcile all orphan events for a specific bed (cama_id) to the current patient.
    
    This is useful for bulk reconciliation when a patient was registered late
    and there are many orphan events from before registration.
    
    Returns summary of processed and skipped events.
    """
    async with _reconcile_lock:
        return await asyncio.to_thread(_do_reconcile_bed, cama_id, limit)


def _do_reconcile_bed(cama_id: str, limit: int = 1000) -> dict:
    """Reconcile all events from a specific bed to the current patient in that bed.
    
    Returns dict with 'processed', 'skipped', and 'patient_name' keys.
    """
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


def _do_reconcile(device_id: str | None = None, limit: int = 100) -> dict:
    """Synchronous reconcile worker. Intended to run in a thread via asyncio.to_thread.

    Returns a dict with keys 'processed' and 'skipped'.
    
    NEW LOGIC: Extract cama_id from payload and find current patient in that bed.
    """
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


def import_alerts_list(alerts: list[dict], db_path: str | None = None) -> int:
    """Helper to import a list of alert dicts into the DB via DAO.

    Returns the number of inserted alerts. This helper is intended to be used
    by the admin import endpoint and by tests.
    """
    if db_path is None:
        db_path = DB_PATH
    # Delegate to DAO which performs validation and timeline logging
    try:
        inserted = inserir_alertas(db_path, alerts)
    except ValueError as exc:
        # normalize to HTTP-like error when used by endpoints; caller can catch
        raise
    return int(inserted)


@router.post("/admin/import_alerts", status_code=status.HTTP_200_OK)
async def api_admin_import_alerts(
    request: Request,
    arquivo: UploadFile | None = File(None),
    body: list[dict] | None = None,
    x_admin_token: str | None = None,
) -> dict:
    """Admin endpoint to import alerts in bulk.

    Security: If environment var UPP_ADMIN_TOKEN is set, callers must send the
    same value in header `X-Admin-Token`. If the env var is not set (dev), the
    endpoint falls back to checking that the request has a `session_user`
    cookie (i.e., a logged-in user).
    """
    # Authorization
    admin_token_env = os.getenv("UPP_ADMIN_TOKEN")
    if admin_token_env:
        # Prefer header-based token
        hdr = request.headers.get("X-Admin-Token") or x_admin_token
        if hdr != admin_token_env:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "forbidden"})
    else:
        # dev fallback: require session cookie
        if not request.cookies.get("session_user"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "not_authenticated"})

    alerts: list[dict] = []
    # If multipart file provided, treat as JSONL
    if arquivo is not None:
        try:
            async for linha in _iterar_jsonl(arquivo):
                alerts.append(json.loads(linha))
        finally:
            await arquivo.close()
    elif body is not None:
        if not isinstance(body, list):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_payload", "message": "Expected an array of alert objects"})
        alerts = body
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "no_payload", "message": "Provide JSON body or upload a JSONL file"})

    # Ensure minimal paciente_fichas exist so frontend can display patientName and cama
    try:
        pacientes = {str(a.get('paciente_id')) for a in alerts if a.get('paciente_id')}
        for pid in pacientes:
            try:
                ensure_minimal_paciente_ficha(DB_PATH, pid)
            except Exception:
                # non-fatal: continue
                pass
    except Exception:
        # If computing pacientes fails, proceed to validation step which will catch malformed alerts
        pass

    try:
        inserted = import_alerts_list(alerts, db_path=DB_PATH)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_alerts", "message": str(exc)}) from exc
    return {"received": len(alerts), "inserted": inserted}


def reset_rate_limiter() -> None:
    """Limpa o estado do rate limiter (uso em testes)."""
    _rate_buckets.clear()


def reset_processador() -> None:
    """Limpa estados incrementais, filtros e metricas (uso em testes)."""
    PROCESSADOR.reset()
    reset_filtro()


class TimelineEventResponse(BaseModel):
    id: int
    paciente_id: str
    paciente_name: str | None = None
    ts: str
    ts_ms: int
    tipo: str
    descricao: str | None = None


@router.get("/timeline", status_code=status.HTTP_200_OK, response_model=list[TimelineEventResponse])
async def timeline_endpoint(
    paciente_id: str | None = None,
    tipo: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 100,
) -> list[TimelineEventResponse]:
    """Retorna eventos da timeline com filtros opcionais.
    
    Query Parameters:
    - paciente_id: str - Filter by patient ID
    - tipo: str - Filter by event type (alert_open, alert_acknowledged, alert_completed, repositioning)
    - start_ms: int - Start timestamp in milliseconds
    - end_ms: int - End timestamp in milliseconds
    - limit: int (default 100) - Maximum number of events to return
    
    Returns events sorted by timestamp descending (newest first).
    """
    if limit is None or limit <= 0:
        limit = 100
    if limit > 1000:
        limit = 1000
        
    events = selecionar_timeline(DB_PATH, paciente_id=paciente_id, start_ms=start_ms, end_ms=end_ms, limit=limit)
    
    # Filter by tipo if specified
    if tipo:
        events = [e for e in events if e.get("tipo") == tipo]
    
    # Sort by timestamp descending (newest first)
    events = sorted(events, key=lambda e: e.get("ts_ms", 0), reverse=True)
    
    # Enrich with patient names
    result = []
    for e in events:
        patient_name = None
        try:
            ficha = obter_ficha_paciente(DB_PATH, e["paciente_id"], incluir_rotinas=False)
            if ficha:
                patient_name = ficha.get("nome")
        except Exception:
            pass
            
        result.append({
            "id": e["id"],
            "paciente_id": e["paciente_id"],
            "paciente_name": patient_name,
            "ts": e["ts"],
            "ts_ms": e["ts_ms"],
            "tipo": e["tipo"],
            "descricao": e["descricao"],
        })
    
    return result


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
async def api_listar_pacientes(incluir_rotinas: bool = False) -> list[FrontendPatient]:
    """Retorna a lista de fichas de pacientes em JSON.

    Query params:
    - incluir_rotinas: bool (default False) para incluir as rotinas associadas.
    """
    fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=incluir_rotinas)
    return [_ficha_to_frontend(ficha) for ficha in fichas]


def _map_perfil_from_frontend(risk: str) -> str:
    mapping = {"high": "alto", "medium": "medio", "low": "baixo"}
    return mapping.get(str(risk).lower(), DEFAULT_PERFIL)


def _map_perfil_to_frontend(perf: str) -> str:
    mapping = {"alto": "high", "medio": "medium", "baixo": "low"}
    return mapping.get(str(perf).lower(), "medium")


def _split_cama(cama: str | None) -> tuple[str | None, str | None]:
    if not cama:
        return None, None
    if "/" in cama:
        parts = [p.strip() for p in cama.split("/")]
        room = parts[0] if parts else None
        bed = parts[1] if len(parts) > 1 else None
        return room, bed
    return cama, None


def _join_cama(room: str | None, bed: str | None) -> str | None:
    if room and bed:
        return f"{room} / {bed}"
    if room:
        return room
    return None


def _ficha_to_frontend(ficha: dict) -> FrontendPatient:
    room, bed = _split_cama(ficha.get("cama_id"))
    perfil = str(ficha.get("perfil") or DEFAULT_PERFIL)
    
    # Calculate repositioning interval based on risk profile (from configuracao.py)
    interval_map = {
        "baixo": 2,   # 120 minutes = 2 hours
        "medio": 2,   # 90 minutes ≈ 1.5 hours (rounded to 2)
        "alto": 1     # 60 minutes = 1 hour
    }
    repositioning_interval = interval_map.get(perfil.lower(), 2)
    
    return FrontendPatient(
        id=str(ficha.get("paciente_id") or ficha.get("paciente_id") or ""),
        name=ficha.get("nome") or "",
        room=room,
        bed=bed,
        riskLevel=_map_perfil_to_frontend(perfil),
        repositioningInterval=repositioning_interval,
        createdAt=ficha.get("created_at"),
        updatedAt=ficha.get("updated_at"),
    )


@router.post("/pacientes", status_code=status.HTTP_201_CREATED, response_model=FrontendPatient)
async def api_criar_paciente(payload: FrontendCreatePatient) -> FrontendPatient:
    # map frontend DTO to DAO fields
    nome = payload.name
    perfil = _map_perfil_from_frontend(payload.riskLevel)
    cama = _join_cama(payload.room, payload.bed)
    try:
        ficha = criar_paciente(DB_PATH, nome=nome, perfil=perfil, cama_id=cama, observacoes=None, rotinas=None)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "db_error", "message": str(exc)}) from exc
    return _ficha_to_frontend(ficha)


class FrontendUpdatePatient(BaseModel):
    name: str | None = None
    room: str | None = None
    bed: str | None = None
    riskLevel: str | None = None
    repositioningInterval: int | None = None


@router.get("/pacientes/{paciente_id}", status_code=status.HTTP_200_OK, response_model=FrontendPatient)
async def api_get_paciente(paciente_id: str) -> FrontendPatient:
    ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=True)
    if ficha is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "paciente_nao_encontrado", "message": "Paciente nao encontrado."})
    return _ficha_to_frontend(ficha)


@router.patch("/pacientes/{paciente_id}", status_code=status.HTTP_200_OK, response_model=FrontendPatient)
async def api_update_paciente(paciente_id: str, payload: FrontendUpdatePatient) -> FrontendPatient:
    # fetch existing ficha to fill defaults
    existing = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=True)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "paciente_nao_encontrado", "message": "Paciente nao encontrado."})
    nome = payload.name if payload.name is not None else existing.get("nome")
    perfil = _map_perfil_from_frontend(payload.riskLevel) if payload.riskLevel is not None else existing.get("perfil")
    cama = _join_cama(payload.room, payload.bed) if (payload.room is not None or payload.bed is not None) else existing.get("cama_id")
    try:
        ficha = atualizar_paciente(DB_PATH, paciente_id, nome=nome, perfil=perfil, cama_id=cama, observacoes=existing.get("observacoes"), rotinas=None)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "db_error", "message": str(exc)}) from exc
    return _ficha_to_frontend(ficha)


@router.delete("/pacientes/{paciente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_paciente(paciente_id: str):
    try:
        removed = remover_paciente(DB_PATH, paciente_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_request", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "delete_error", "message": str(exc)}) from exc
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Paciente nao encontrado."})
    return None


# Simulation models
class SimulationRequest(BaseModel):
    """Requisição para gerar dados simulados."""
    duracao_horas: int = Field(..., ge=1, le=72, description="Duração em horas (1-72)")
    seed: int | None = Field(default=42, description="Seed para reproduzibilidade")
    perfil: str = Field(..., description="Perfil de risco: baixo, medio, alto")

    @field_validator('perfil')
    def validate_perfil(cls, v):
        if v not in ['baixo', 'medio', 'alto']:
            raise ValueError('Perfil deve ser: baixo, medio ou alto')
        return v


class SimulationResult(BaseModel):
    """Resultado da simulação."""
    success: bool
    eventos: int
    alertas: int
    duracao: int
    error: str | None = None
    message: str | None = None


@router.post("/pacientes/{paciente_id}/simular", status_code=status.HTTP_200_OK, response_model=SimulationResult)
async def api_simular_paciente(paciente_id: str, payload: SimulationRequest) -> SimulationResult:
    """Gera dados simulados para um paciente.
    
    Isso cria:
    1. N horas de dados de postura (1 evento a cada 5 minutos)
    2. Processa alertas baseado no perfil
    3. Salva tudo no banco de dados
    
    Args:
        paciente_id: ID do paciente
        payload: Requisição com duração, seed e perfil
        
    Returns:
        SimulationResult com números de eventos e alertas gerados
    """
    logger = structlog.get_logger(__name__)
    
    try:
        # 1. Verificar se paciente existe
        ficha = obter_ficha_paciente(DB_PATH, paciente_id)
        if ficha is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "paciente_nao_encontrado", "message": f"Paciente {paciente_id} nao encontrado."}
            )
        
        logger.info("simulacao_iniciada", paciente_id=paciente_id, duracao_horas=payload.duracao_horas, perfil=payload.perfil)
        
        # 2. Gerar dados simulados
        try:
            # Mapear nível de risco para perfil
            perfil_key = payload.perfil.lower() if payload.perfil else "medio"
            perfil_params = PERFIS_PREDEFINIDOS.get(perfil_key, PERFIS_PREDEFINIDOS["medio"])
            perfil = PerfilPaciente(**perfil_params)
            
            df_grade, contextos = gerar_sessao_simulada(
                duracao_horas=payload.duracao_horas,
                seed=payload.seed or 42,
                passo_min=5,
                perfil=perfil,
                incluir_contexto=True
            )
        except Exception as e:
            logger.error("simulacao_gerar_erro", error=str(e), paciente_id=paciente_id)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "simulacao_erro", "message": f"Erro ao gerar dados: {str(e)}"}
            ) from e
        
        # 3. Adicionar ID do paciente ao DataFrame
        df_grade.insert(0, "paciente_id", paciente_id)
        
        # 4. Salvar grades no banco de dados
        try:
            inserir_grade(DB_PATH, df_grade, paciente_id=paciente_id)
            logger.info("simulacao_grade_salva", paciente_id=paciente_id, num_eventos=len(df_grade))
        except Exception as e:
            logger.error("simulacao_salvar_grade_erro", error=str(e), paciente_id=paciente_id)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "db_error", "message": f"Erro ao salvar grades: {str(e)}"}
            ) from e
        
        # 5. Processar alertas
        try:
            _, alertas = processar_alertas(
                df_grade[["timestamp", "postura"]],
                payload.perfil,
                paciente_id
            )
            logger.info("simulacao_alertas_processados", paciente_id=paciente_id, num_alertas=len(alertas))
        except Exception as e:
            logger.error("simulacao_processar_alertas_erro", error=str(e), paciente_id=paciente_id)
            alertas = []
        
        # 6. Salvar alertas no banco de dados
        if alertas:
            try:
                inserir_alertas(DB_PATH, alertas)
                logger.info("simulacao_alertas_salvos", paciente_id=paciente_id, num_alertas=len(alertas))
            except Exception as e:
                logger.warning("simulacao_salvar_alertas_erro", error=str(e), paciente_id=paciente_id)
        
        logger.info("simulacao_concluida", paciente_id=paciente_id, eventos=len(df_grade), alertas=len(alertas))
        
        # Invalidate cache so new alerts appear immediately
        await api_cache.clear()
        
        return SimulationResult(
            success=True,
            eventos=len(df_grade),
            alertas=len(alertas),
            duracao=payload.duracao_horas,
            message=f"Simulacao concluida: {len(df_grade)} eventos, {len(alertas)} alertas"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("simulacao_erro_desconhecido", error=str(e), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "internal_error", "message": f"Erro interno: {str(e)}"}
        ) from e


# WebSocket endpoint for ESP32 firmware real-time event ingestion
@router.websocket("/ws/eventos")
async def websocket_eventos(websocket: WebSocket):
    """WebSocket endpoint para ingesto de eventos em tempo real do ESP32.
    
    Protocolo:
    1. ESP32 envia JSON de autenticação: {"device_id": "DEV-001", "cama_id": "C-01"}
    2. Servidor responde com ACK
    3. ESP32 envia eventos JSON linha por linha
    4. Servidor processa incrementalmente
    5. Servidor responde com {"status": "ok", "seq": <seq>} para cada evento
    
    Exemplo de evento:
    {
        "seq": 1,
        "device_id": "DEV-001",
        "paciente_id": "PAC-001",
        "cama_id": "C-01",
        "ts_utc": "2025-10-27T14:30:00Z",
        "tipo": "postura",
        "valor": 1,
        "confianca": 0.95
    }
    """
    await websocket.accept()
    device_id = None
    paciente_id = None
    logger = structlog.get_logger(__name__)
    
    try:
        # 1. Receber autenticação
        auth_msg = await websocket.receive_text()
        auth = json.loads(auth_msg)
        device_id = auth.get("device_id")
        cama_id = auth.get("cama_id")
        
        if not device_id or not cama_id:
            await websocket.send_json({"error": "device_id e cama_id obrigatórios"})
            await websocket.close()
            return
        
        logger.info("ws_eventos_conectado", device_id=device_id, cama_id=cama_id)
        
        # 2. Registrar dispositivo e resolver paciente
        try:
            registrar_device(DB_PATH, device_id, meta={"cama_id": cama_id})
        except Exception as e:
            logger.warning("ws_registrar_device_erro", error=str(e))
        
        # 3. Tentar resolver paciente da câmara
        try:
            paciente_id = resolver_paciente_por_device_em(DB_PATH, device_id, int(time.time() * 1000))
        except Exception:
            pass
        
        # 4. Enviar ACK de conexão
        await websocket.send_json({
            "status": "connected",
            "device_id": device_id,
            "paciente_id": paciente_id,
            "message": "Conectado ao servidor de eventos"
        })
        
        # 5. Loop de processamento de eventos
        eventos_processados = 0
        while True:
            data = await websocket.receive_text()
            try:
                evento_json = json.loads(data)
                seq = evento_json.get("seq", 0)
                
                # Normalizar evento
                if "device_id" not in evento_json:
                    evento_json["device_id"] = device_id
                if "paciente_id" not in evento_json and paciente_id:
                    evento_json["paciente_id"] = paciente_id
                
                # Processar evento através do filtro
                resultado = filtrar_evento(evento_json)
                
                # DEBUG: Log detalhado do resultado do filtro
                logger.info(
                    "ws_filtro_resultado",
                    device_id=device_id,
                    seq=seq,
                    descartado=resultado.descartado,
                    motivo=resultado.motivo,
                    prontos_count=len(resultado.prontos),
                    buffered=resultado.buffered
                )
                
                alertas_gerados = []
                if not resultado.descartado and resultado.prontos:
                    # Inserir no banco de dados
                    try:
                        inserir_eventos(DB_PATH, evento_json["paciente_id"], [evento_json])
                        metricas.registrar_recebido()
                        eventos_processados += 1
                        logger.info("ws_evento_salvo", device_id=device_id, seq=seq, paciente_id=evento_json["paciente_id"])
                    except Exception as e:
                        logger.warning("ws_insert_erro", device_id=device_id, seq=seq, error=str(e))
                    
                    # ✅ NOVO: Processar alertas incrementalmente
                    try:
                        logger.info("ws_processando_alertas", device_id=device_id, eventos_count=len(resultado.prontos))
                        alertas_gerados = PROCESSADOR.processar_lote(resultado.prontos)
                        logger.info("ws_alertas_processados", device_id=device_id, alertas_count=len(alertas_gerados))
                        
                        if alertas_gerados:
                            # Salvar alertas no banco de dados
                            inserir_alertas(DB_PATH, evento_json["paciente_id"], alertas_gerados)
                            
                            # Broadcast para clientes conectados em /ws/alerts
                            for alerta in alertas_gerados:
                                # Determinar severidade baseado no perfil
                                perfil = alerta.get("perfil", "medio").lower()
                                if perfil == "alto":
                                    severity = "critical"
                                elif perfil == "medio":
                                    severity = "high"
                                else:
                                    severity = "medium"
                                
                                # Criar mensagem de broadcast
                                broadcast_msg = {
                                    "type": "alert_new",
                                    "alert_id": alerta.get("inicio"),
                                    "patient_id": alerta.get("paciente_id"),
                                    "timestamp": alerta.get("inicio"),
                                    "status": "pending",
                                    "severity": severity,
                                    "data": alerta
                                }
                                
                                # Enviar via WebSocket (não bloquear)
                                asyncio.create_task(ws_manager_optimized.broadcast(broadcast_msg))
                            
                            logger.info(
                                "ws_alertas_gerados",
                                device_id=device_id,
                                seq=seq,
                                paciente_id=evento_json["paciente_id"],
                                quantidade=len(alertas_gerados)
                            )
                    
                    except Exception as e:
                        logger.error("ws_processar_alertas_erro", device_id=device_id, seq=seq, error=str(e))
                
                elif resultado.descartado:
                    logger.warning("ws_evento_descartado", device_id=device_id, seq=seq, motivo=resultado.motivo)
                else:
                    logger.info("ws_evento_bufferizado", device_id=device_id, seq=seq)
                
                # Enviar ACK
                await websocket.send_json({
                    "status": "ok",
                    "seq": seq,
                    "processados": eventos_processados,
                    "descartado": resultado.descartado,
                    "alertas_gerados": len(alertas_gerados)
                })
                
            except json.JSONDecodeError as e:
                logger.warning("ws_json_erro", device_id=device_id, error=str(e))
                await websocket.send_json({
                    "status": "error",
                    "error": "JSON inválido"
                })
            except Exception as e:
                logger.warning("ws_evento_erro", device_id=device_id, error=str(e))
                await websocket.send_json({
                    "status": "error",
                    "error": str(e)
                })
    
    except WebSocketDisconnect:
        logger.info("ws_eventos_desconectado", device_id=device_id, eventos=eventos_processados if device_id else 0)
    except Exception as e:
        logger.error("ws_eventos_erro", device_id=device_id, error=str(e))


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
        logger.error("csv_export_error", error=str(e), user=user if 'user' in locals() else None)
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
        logger.error("pdf_export_error", error=str(e), user=user if 'user' in locals() else None)
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


