from __future__ import annotations

import time
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

# Import shared constants and functions
from interface.api_shared import (
    DB_PATH, 
    APP_VERSION, 
    APP_START_TIME, 
    _reset_auth_rate_limits,
    reset_rate_limiter,
    _rate_buckets,
    _aplicar_rate_limit
)

# Import routers
from interface.routers import (
    auth,
    pacientes,
    devices,
    alerts,
    dashboard,
    ingestao,
    backup,
    admin
)
from interface import endpoints_agenda

# Import symbols needed for tests (Facade pattern)
# These are re-exported so that 'from interface.api import PROCESSADOR' works
from interface.routers.ingestao import PROCESSADOR, reconcile_device_events
from interface.routers.alerts import frontend_alerts
from quality.filtro import reset_filtro

# Create App
app = FastAPI(
    title="Sistema de Monitoramento de Pacientes",
    description="API para monitoramento de pacientes acamados e prevencao de LPP",
    version=APP_VERSION,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create main router to aggregate all modules
router = APIRouter(prefix="/api")
router.include_router(auth.router)
router.include_router(pacientes.router)
router.include_router(devices.router)
router.include_router(alerts.router)
router.include_router(dashboard.router)
router.include_router(ingestao.router)
router.include_router(backup.router)
router.include_router(admin.router)
router.include_router(endpoints_agenda.router)

# Include the main router in the app
app.include_router(router)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Sistema de Monitoramento de Pacientes API",
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - APP_START_TIME),
        "docs": "/docs",
    }

# Health check
@app.get("/health")
async def health_check():
    return {"status": "ok", "db": DB_PATH}

# Test helpers (Facade)
def reset_processador() -> None:
    """Limpa estados incrementais, filtros e metricas (uso em testes)."""
    PROCESSADOR.reset()
    reset_filtro()


