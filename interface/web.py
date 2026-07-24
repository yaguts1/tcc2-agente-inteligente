"""App FastAPI: monta a API (interface.api) e serve a SPA React buildada.

Execute com:
    uvicorn interface.web:app --reload

A antiga UI server-side em Jinja/HTMX (páginas de paciente, ações de alerta,
timeline, documentos) foi removida — a interface real é a SPA React em
`frontend/`. Aqui ficam só: bootstrap do app, middlewares, lifespan (schema +
tasks de background), healthcheck/metrics e o mount dos estáticos da SPA.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict

import structlog
from fastapi import APIRouter, FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from interface.api import router as api_router
from interface.db_core import criar_esquema
from interface.lifespan_tasks import (
    start_reconciler_task,
    stop_reconciler_task,
    start_backup_task,
    stop_backup_task,
)
from configuracao import carregar_configuracao
from servicos import metricas

logger = structlog.get_logger(__name__)

config = carregar_configuracao()
DB_PATH = config.db_path
BACKUP_DIR = os.getenv("UPP_BACKUP_DIR", "backups")
APP_PREFIX = os.getenv("APP_PREFIX", "")


# --- Middlewares -----------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Coleta métricas Prometheus de todas as requisições."""

    async def dispatch(self, request, call_next):
        import time
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        method = request.method
        path = request.url.path
        status_code = response.status_code

        # Simplifica o path para as métricas (remove IDs)
        endpoint = path
        for pattern in ["/api/frontend/alerts/", "/api/pacientes/"]:
            if pattern in path:
                parts = path.split(pattern)
                if len(parts) > 1:
                    endpoint = f"{pattern}{{id}}"
                    break

        metricas.registrar_request(method, endpoint, status_code, duration)
        return response


# --- Lifespan --------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Garante o schema no startup (aplica migrations pendentes; não-fatal).
    try:
        criar_esquema(DB_PATH)
        logger.info("schema_garantido", db_path=DB_PATH)
    except Exception as exc:  # pragma: no cover - log but do not fail startup
        logger.warning("schema_nao_garantido", motivo=str(exc))

    # Tasks de background (reconciler de device_events + backup periódico).
    start_reconciler_task(app)
    start_backup_task(app, DB_PATH, BACKUP_DIR)

    try:
        yield
    finally:
        await stop_reconciler_task(app)
        await stop_backup_task(app)


app = FastAPI(title="Monitor de Alertas UPP", lifespan=_lifespan)
web_router = APIRouter()

app.add_middleware(PrometheusMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS: as portas de dev local vêm por padrão; domínios de produção entram via
# ALLOWED_ORIGINS (separados por vírgula), sem precisar editar código.
_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_extra_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
_allowed_origins = _DEV_ORIGINS + _extra_origins
try:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception:
    # não falhar o startup se o middleware não puder ser adicionado
    pass


# --- Detecção da SPA buildada ---------------------------------------------
# O Vite deste repo builda para frontend/build (ver frontend/vite.config.ts).
_ROOT = Path(__file__).resolve().parents[1]
_candidates = [
    _ROOT / "frontend" / "build",
    _ROOT / "frontend" / "dist",
    _ROOT / "frontend",
]
SITE_UI_DIST = None
for cand in _candidates:
    if (cand / "index.html").exists():
        SITE_UI_DIST = cand
        break


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    if SITE_UI_DIST and (SITE_UI_DIST / "favicon.ico").exists():
        return FileResponse(str(SITE_UI_DIST / "favicon.ico"))
    return Response(status_code=404)


@web_router.get("/metrics")
def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@web_router.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


# Monta os routers ANTES dos estáticos (para as rotas de API terem precedência).
app.include_router(web_router, prefix=APP_PREFIX)
app.include_router(api_router, prefix=APP_PREFIX)


# Healthcheck global (fora do prefixo) — usado pelo healthcheck do Docker.
@app.get("/healthz")
def global_health_check() -> Dict[str, str]:
    return {"status": "ok"}


# Serve a SPA buildada sob APP_PREFIX (ex: /TCC/). Fallback de index.html para
# rotas não-API é tratado pelo StaticFiles(html=True).
if SITE_UI_DIST is not None:
    try:
        mount_path = APP_PREFIX if APP_PREFIX else "/"
        app.mount(mount_path, StaticFiles(directory=str(SITE_UI_DIST), html=True), name="site_ui")
    except Exception:
        # não falhar se o mount dos estáticos não for possível
        SITE_UI_DIST = None
