"""Agregador dos routers da API.

CONVENÇÃO — `def` vs `async def` nos handlers
---------------------------------------------
Este projeto acessa SQLite de forma síncrona e bloqueante. No FastAPI:

- handler `def`        -> roda num threadpool, o event loop segue livre;
- handler `async def`  -> roda NO event loop; qualquer chamada bloqueante ali
                          trava todas as outras requisições e WebSockets.

Portanto: **declare o handler como `def`** a menos que ele realmente precise de
`await` (ex.: `await request.json()`, chamar um serviço assíncrono). Se precisar
ser `async` e houver trabalho bloqueante ou pesado em CPU, mande para uma thread
com `asyncio.to_thread(...)` — é o que `routers/auth.py` faz com o bcrypt e o
`services/alerts_service.py` com as operações em lote.

Havia ~25 handlers declarados `async def` sem um único `await` no corpo, todos
fazendo I/O de banco no event loop; o caso extremo era o `/simular`, que rodava
uma geração de dados inteira com pandas e travava o servidor durante a operação.
"""
from __future__ import annotations

from fastapi import APIRouter

# Import shared constants and functions
from interface.api_shared import (
    DB_PATH,
    _reset_auth_rate_limits,
    reset_rate_limiter,
    _rate_buckets,
    _aplicar_rate_limit
)

# Import routers
from interface.routers import auditoria, usuarios
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
# These are re-exported so that 'from interface.api import PROCESSADOR' works.
#
# Vêm do SERVIÇO, não do router: o router apenas os importava para uso próprio,
# e puxá-los de lá fazia dele um intermediário acidental na cadeia de imports.
from interface.services.ingestao_service import PROCESSADOR, reconcile_device_events
from interface.routers.alerts import frontend_alerts
from quality.filtro import reset_filtro

# `__all__` declara que estes nomes sao REEXPORTS intencionais desta
# fachada, e nao imports esquecidos. Sem isso o `ruff --fix` os remove
# como F401 (nada os referencia dentro do arquivo) e derruba a
# aplicacao no import — foi exatamente o que aconteceu ao ligar o lint.
__all__ = [
    "APIRouter",
    "DB_PATH",
    "PROCESSADOR",
    "_aplicar_rate_limit",
    "_rate_buckets",
    "_reset_auth_rate_limits",
    "admin",
    "alerts",
    "annotations",
    "auditoria",
    "auth",
    "backup",
    "dashboard",
    "devices",
    "endpoints_agenda",
    "frontend_alerts",
    "ingestao",
    "pacientes",
    "reconcile_device_events",
    "reset_filtro",
    "reset_rate_limiter",
    "usuarios",
]

# Create main router to aggregate all modules. Mounted into the real app
# (interface.web:app, the only app actually served — see Dockerfile) with
# the "/api" prefix already baked in here.
router = APIRouter(prefix="/api")
router.include_router(auth.router)
router.include_router(pacientes.router)
router.include_router(pacientes.router_dispositivos)
router.include_router(devices.router)
router.include_router(alerts.router)
router.include_router(dashboard.router)
router.include_router(ingestao.router)
router.include_router(backup.router)
router.include_router(admin.router)
# IMPORTANTE: router_proprio ANTES de usuarios.router. O FastAPI casa rotas na
# ordem de registro, e /usuarios/eu/senha casaria com /usuarios/{username}/senha
# (do router administrativo) se este viesse primeiro — o usuario receberia 403
# ao tentar trocar a propria senha. Mesmo problema que /agenda/check ja teve.
router.include_router(usuarios.router_proprio)
router.include_router(usuarios.router)
router.include_router(auditoria.router)
router.include_router(endpoints_agenda.router)

# Test helpers (Facade)
def reset_processador() -> None:
    """Limpa estados incrementais, filtros e metricas (uso em testes)."""
    PROCESSADOR.reset()
    reset_filtro()


