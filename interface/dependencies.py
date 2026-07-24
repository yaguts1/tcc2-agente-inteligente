from typing import Optional

from fastapi import Request, HTTPException, status
from interface.auth_utils import verify_token


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
