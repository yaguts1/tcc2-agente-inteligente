import os
import secrets
from typing import Optional

import structlog
from fastapi import Request, HTTPException, status
from interface.auth_utils import verify_token

logger = structlog.get_logger(__name__)

TOKEN_DISPOSITIVO_HEADER = "X-Device-Token"


def token_dispositivo_configurado() -> Optional[str]:
    """Token compartilhado que os ESP32 apresentam, ou None se nao configurado."""
    return os.getenv("UPP_DEVICE_TOKEN") or None


def verificar_token_dispositivo(request: Request) -> None:
    """Autentica o dispositivo nos endpoints de ingestao.

    O firmware so envia `X-Device-Id`, que ele mesmo escolhe — nao e segredo
    nenhum, e ainda permite furar o rate limit trocando o header. Este token e
    o que de fato autentica a origem dos dados.

    Se UPP_DEVICE_TOKEN nao estiver definido, a verificacao fica desligada para
    nao derrubar bancadas ja montadas; o aviso sai no startup (interface/web.py).
    """
    esperado = token_dispositivo_configurado()
    if not esperado:
        return

    recebido = request.headers.get(TOKEN_DISPOSITIVO_HEADER, "")
    if not recebido or not secrets.compare_digest(recebido, esperado):
        logger.warning(
            "device_token_invalido",
            device_id=request.headers.get("X-Device-Id"),
            cliente=request.client.host if request.client else None,
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "device_nao_autenticado", "message": "Token de dispositivo invalido."},
        )


def usuario_de_jwt(request: Request) -> Optional[str]:
    """Extrai o usuário de um JWT válido — header `Authorization: Bearer <jwt>`
    ou cookie `access_token`. Retorna None se não houver JWT válido.

    NÃO confia no cookie `session_user` (texto puro, não assinado, forjável):
    qualquer um poderia mandar `Cookie: session_user=admin` e ser autenticado.
    A identidade só vem de um token assinado verificado por `verify_token`.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = verify_token(auth_header[7:])
        if payload:
            return payload.get("sub")

    token_cookie = request.cookies.get("access_token")
    if token_cookie:
        payload = verify_token(token_cookie)
        if payload:
            return payload.get("sub")

    return None


async def get_current_user(request: Request) -> str:
    """Dependency FastAPI: retorna o username autenticado (via JWT) ou 401."""
    user = usuario_de_jwt(request)
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "not_authenticated", "message": "Authentication required"},
        )
    return user
