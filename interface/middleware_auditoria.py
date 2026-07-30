"""Middleware que alimenta a trilha de auditoria.

Por que middleware, e nao chamadas explicitas em cada endpoint: uma trilha que
depende de alguem lembrar de chamar `registrar()` tem cobertura incompleta por
construcao — e o endpoint esquecido e justamente o que ninguem audita. Aqui
todo acesso a rota de dado clinico e registrado por padrao; esquecer exige
remover uma rota da lista, o que e visivel.

O que fica de fora, de proposito:
  * /healthz e assets da SPA — nao tocam dado de paciente e inundariam a trilha;
  * /api/auth/login — a senha vai no corpo; registramos apenas o resultado
    (sucesso/falha), sem corpo, para nao arriscar gravar credencial.

Nada do CORPO da requisicao ou da resposta e gravado: alem de volume, o corpo
carrega justamente o dado sensivel que a trilha existe para proteger. O que
interessa e QUEM acessou O QUE e QUANDO.
"""

from __future__ import annotations

import asyncio
import re
import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# Rotas cujo acesso e auditado (casadas contra o caminho sem o APP_PREFIX).
_ROTAS_AUDITADAS = re.compile(
    r"^/api/("
    r"pacientes"
    r"|frontend/alerts"
    r"|timeline"
    r"|stats"
    r"|alerts/export"
    r"|admin"
    r"|usuarios"
    r"|devices"
    r"|device_events"
    r"|auditoria"
    r")"
)

# Identificadores de paciente aparecem como /pacientes/PAC-0001/... ou
# /pacientes/cama/{cama}. Extrair da rota permite responder "quem acessou os
# dados deste paciente?", que e a pergunta central da LGPD.
_PACIENTE_NA_ROTA = re.compile(r"/pacientes/(?!cama/)([^/]+)")


class AuditoriaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        caminho = request.url.path
        prefixo = getattr(request.app.state, "app_prefix", "") or ""
        relativo = caminho[len(prefixo):] if prefixo and caminho.startswith(prefixo) else caminho

        if not _ROTAS_AUDITADAS.match(relativo):
            return await call_next(request)

        inicio = time.perf_counter()
        response = await call_next(request)
        duracao_ms = int((time.perf_counter() - inicio) * 1000)

        try:
            from interface.api_shared import DB_PATH, ip_do_cliente
            from interface.dependencies import _payload_do_jwt
            from interface.auditoria_contexto import pacientes_declarados
            from interface.repositories.auditoria import registrar

            payload = _payload_do_jwt(request) or {}

            # QUEM foi afetado. Duas fontes, nesta ordem:
            #
            #  1. o que o handler DECLAROU (`interface/auditoria_contexto.py`).
            #     E o unico caminho possivel quando os identificadores viajam no
            #     CORPO — o caso das operacoes em lote, que sao a escrita de
            #     maior volume do sistema e auditavam `paciente_id = NULL`;
            #  2. o caminho da requisicao, que resolve as rotas por paciente.
            #
            # Uma linha POR PACIENTE, e nao uma linha com a lista. A pergunta do
            # Art. 48 da LGPD e "quais titulares foram afetados", e responde-la
            # com um `LIKE` sobre uma coluna JSON seria fragil e lento
            # justamente no momento em que ela e feita — durante um incidente.
            declarados = pacientes_declarados(request)
            if not declarados:
                match = _PACIENTE_NA_ROTA.search(relativo)
                declarados = [match.group(1)] if match else []

            # A escrita vai para uma thread: este middleware roda no event loop
            # e um INSERT sincrono aqui bloquearia todas as outras requisicoes.
            #
            # `[None]` quando nao ha paciente identificado preserva o
            # comportamento anterior para as rotas que nao sao por paciente
            # (`/api/stats`, `/api/admin`): elas seguem gerando uma linha.
            for paciente in declarados or [None]:
                await asyncio.to_thread(
                    registrar,
                    DB_PATH,
                    metodo=request.method,
                    rota=relativo,
                    status=response.status_code,
                    usuario=payload.get("sub"),
                    papel=payload.get("role"),
                    paciente_id=paciente,
                    ip=ip_do_cliente(request),
                    duracao_ms=duracao_ms,
                    # Marca a linha como parte de uma operacao em lote. Sem
                    # isto, 30 fechamentos de um clique em "selecionar tudo"
                    # sao indistinguiveis de 30 decisoes individuais — e essa
                    # diferenca e o cerne de "acao em lote fabrica
                    # documentacao".
                    detalhe=(
                        {"lote": True, "pacientes_no_lote": len(declarados)}
                        if len(declarados) > 1
                        else None
                    ),
                )
        except Exception:
            # Auditar nunca pode derrubar a resposta ja produzida — mas a falha
            # precisa aparecer, senao a trilha para de gravar em silencio.
            logger.warning("auditoria_middleware_falhou", rota=relativo, exc_info=True)

        return response
