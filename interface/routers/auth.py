from __future__ import annotations

import json
import os
import secrets
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from passlib.hash import bcrypt

from interface.repositories.users import UserRepository
from interface.api_shared import _check_auth_rate_limit, DB_PATH
from interface.schemas import RegisterRequest
from interface.auth_utils import ACCESS_TOKEN_EXPIRE_SECONDS, create_access_token, em_producao
from interface.dependencies import get_current_user

router = APIRouter(tags=["auth"])
user_repo = UserRepository(DB_PATH)


def _requisicao_e_https(request: Request) -> bool:
    """Detecta HTTPS considerando o proxy reverso.

    O Caddy termina o TLS e fala HTTP com o app, entao request.url.scheme e
    sempre "http" aqui (o uvicorn nao roda com --proxy-headers); quem carrega a
    informacao e o X-Forwarded-Proto que o Caddy injeta.
    """
    encaminhado = request.headers.get("X-Forwarded-Proto", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _definir_cookie_sessao(response: Response, request: Request, token: str) -> None:
    """Grava o cookie de sessao com as flags de seguranca corretas.

    - samesite="lax": a API usa allow_credentials=True no CORS; sem SameSite o
      cookie seria enviado em requisicoes cross-site e todo endpoint que muda
      estado ficaria exposto a CSRF.
    - secure quando a requisicao veio por HTTPS: impede o cookie de trafegar em
      texto claro. Nao pode ser amarrado a ENVIRONMENT: o container roda com
      ENVIRONMENT=production e ainda publica a porta 8000 em HTTP para debug
      local — marcar Secure ali faria o browser descartar o cookie e o login
      simplesmente nao funcionaria.

    Nao grava mais o cookie `session_user`: era texto puro, nao assinado e
    forjavel (interface/dependencies.py ja o ignorava ha tempos), entao
    continuar emitindo-o so convidava a voltar a confiar nele.
    """
    response.set_cookie(
        "access_token",
        token,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_requisicao_e_https(request),
    )


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
        user = user_repo.get_by_username(username)
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
        # Fallback legado por variavel de ambiente, para bancada/dev.
        #
        # Antes bastava a senha bater: como este ramo so roda quando o usuario
        # NAO existe no banco, qualquer nome inventado + UPP_ADMIN_PASS emitia
        # um JWT valido com aquele `sub` arbitrario. Agora exige tambem que o
        # username seja o admin configurado, e o caminho fica indisponivel em
        # producao (la a autenticacao tem que passar pelo banco).
        if em_producao():
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_credentials", "message": "Usuario ou senha invalidos"},
            )
        admin_pass = os.getenv("UPP_ADMIN_PASS")
        admin_user = os.getenv("UPP_ADMIN_USER", "admin")
        credenciais_ok = bool(admin_pass) and (
            secrets.compare_digest(username, admin_user)
            and secrets.compare_digest(password, admin_pass)
        )
        if not credenciais_ok:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_credentials", "message": "Usuario ou senha invalidos"})

    # Generate JWT token
    token_data = {"sub": username, "role": user.get("role", "staff") if user else "staff"}
    token = create_access_token(token_data)
    
    # set cookie for session
    resp = {"username": username, "token": token, "display_name": user.get("display_name") if user else None, "role": user.get("role", "staff") if user else "staff"}

    response = Response(content=json.dumps(resp), media_type="application/json", status_code=status.HTTP_200_OK)
    _definir_cookie_sessao(response, request, token)
    return response


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
        user_repo.create(username, password_hash, display)
    except ValueError as exc:
        structlog.get_logger(__name__).warning("register_failed_user_exists", username=username, motivo=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "user_exists", "message": str(exc)})
    except Exception as exc:
        structlog.get_logger(__name__).exception("register_db_error", username=username, erro=str(exc))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "db_error", "message": str(exc)})

    # auto-login after register: set cookie
    
    # Generate JWT token
    token_data = {"sub": username, "role": "staff"}
    token = create_access_token(token_data)

    resp = {"username": username, "display_name": display, "token": token, "role": "staff"}
    response = Response(content=json.dumps(resp), media_type="application/json", status_code=status.HTTP_201_CREATED)
    _definir_cookie_sessao(response, request, token)
    return response


@router.post("/auth/logout", status_code=status.HTTP_200_OK)
async def api_logout() -> dict:
    response = Response(content=json.dumps({"ok": True}), media_type="application/json", status_code=status.HTTP_200_OK)
    response.delete_cookie("session_user")
    response.delete_cookie("access_token")
    return response


@router.get("/auth/me", status_code=status.HTTP_200_OK)
async def api_me(user: str = Depends(get_current_user)) -> dict:
    # Autenticação via get_current_user (JWT only) — não confia mais no
    # cookie session_user forjável.
    # try to include display_name and role when available
    try:
        u = user_repo.get_by_username(user)
        display = None if u is None else u.get("display_name")
        role = "staff" if u is None else (u.get("role") or "staff")
    except Exception:
        display = None
        role = "staff"
    return {"username": user, "display_name": display, "role": role}
