from __future__ import annotations

import json
import os
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from passlib.hash import bcrypt

from interface.repositories.users import UserRepository
from interface.api_shared import _check_auth_rate_limit, DB_PATH
from interface.schemas import RegisterRequest
from interface.auth_utils import create_access_token
from interface.dependencies import get_current_user

router = APIRouter(tags=["auth"])
user_repo = UserRepository(DB_PATH)

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
        # fallback to legacy env var password for quick dev (keeps backward compatibility).
        # No default: if UPP_ADMIN_PASS isn't set, this login path is simply unavailable
        # (a hardcoded default here would be a login bypass with a known password).
        admin_pass = os.getenv("UPP_ADMIN_PASS")
        if not admin_pass or password != admin_pass:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_credentials", "message": "Usuario ou senha invalidos"})

    # Generate JWT token
    token_data = {"sub": username, "role": user.get("role", "staff") if user else "staff"}
    token = create_access_token(token_data)
    
    # set cookie for session
    resp = {"username": username, "token": token, "display_name": user.get("display_name") if user else None, "role": user.get("role", "staff") if user else "staff"}

    response = Response(content=json.dumps(resp), media_type="application/json", status_code=status.HTTP_200_OK)
    # cookie lasts for 8 hours
    response.set_cookie("session_user", username, max_age=8 * 3600, httponly=True)
    response.set_cookie("access_token", token, max_age=8 * 3600, httponly=True)
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
    response.set_cookie("session_user", username, max_age=8 * 3600, httponly=True)
    response.set_cookie("access_token", token, max_age=8 * 3600, httponly=True)
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
