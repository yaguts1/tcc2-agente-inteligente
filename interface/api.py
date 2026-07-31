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
    admin,
    lesoes,
    braden,
    push,
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

# Versao corrente da API. Ver `router` abaixo.
API_VERSAO_ATUAL = "v1"

# As rotas, SEM prefixo. Montadas mais abaixo em `/api` e em `/api/v1`.
#
# Antes o prefixo `/api` vinha embutido aqui, o que impedia servir o mesmo
# conjunto em dois caminhos.
_rotas = APIRouter()
_rotas.include_router(auth.router)
_rotas.include_router(pacientes.router)
_rotas.include_router(pacientes.router_dispositivos)
_rotas.include_router(devices.router)
_rotas.include_router(alerts.router)
_rotas.include_router(dashboard.router)
_rotas.include_router(ingestao.router)
_rotas.include_router(backup.router)
_rotas.include_router(admin.router)
# IMPORTANTE: router_proprio ANTES de usuarios.router. O FastAPI casa rotas na
# ordem de registro, e /usuarios/eu/senha casaria com /usuarios/{username}/senha
# (do router administrativo) se este viesse primeiro — o usuario receberia 403
# ao tentar trocar a propria senha. Mesmo problema que /agenda/check ja teve.
_rotas.include_router(usuarios.router_proprio)
_rotas.include_router(usuarios.router)
_rotas.include_router(auditoria.router)
_rotas.include_router(lesoes.router)
_rotas.include_router(push.router)
_rotas.include_router(braden.router)
_rotas.include_router(endpoints_agenda.router)


@_rotas.get("/versoes", tags=["meta"])
def listar_versoes() -> dict:
    """Versoes da API atendidas por esta instalacao.

    Existe para o prefixo versionado ser DESCOBRIVEL. Sem isto, `/api/v1`
    responderia sem que nenhum consumidor tivesse como saber que ele existe — e
    um mecanismo de versionamento que ninguem encontra nao serve para nada.
    """
    return {
        "atual": API_VERSAO_ATUAL,
        "versoes": [API_VERSAO_ATUAL],
        # `/api` sem versao continua atendendo, e responde exatamente o mesmo:
        # e o que a SPA e o firmware ja instalados usam.
        "sem_versao_atendido": True,
    }


# O router montado no app (interface.web:app, o unico servido — ver Dockerfile).
#
# O MESMO conjunto de rotas atende em dois caminhos:
#
#   /api/...      caminho historico, usado pela SPA e pelo firmware ja
#                 instalados. Continua sendo o documentado.
#   /api/v1/...   caminho versionado, para um consumidor poder FIXAR a versao e
#                 nao ser quebrado por uma mudanca futura.
#
# O versionado sai do schema (`include_in_schema=False`) de proposito. Hoje os
# dois sao identicos POR CONSTRUCAO — sao o mesmo objeto montado duas vezes —,
# entao documentar ambos dobraria o `openapi.json` e os tipos gerados a partir
# dele sem acrescentar UMA informacao. Quem descobre a versao usa
# `GET /api/versoes`.
#
# No dia em que `/api/v1` divergir de `/api` — que e quando versionar passa a
# valer o custo — e ele que vira o documentado, e o `/api` sem versao e que
# passa a ser o alias oculto.
router = APIRouter()
router.include_router(_rotas, prefix="/api")
router.include_router(_rotas, prefix=f"/api/{API_VERSAO_ATUAL}", include_in_schema=False)

# Test helpers (Facade)
def reset_processador() -> None:
    """Limpa estados incrementais, filtros e metricas (uso em testes)."""
    PROCESSADOR.reset()
    reset_filtro()


