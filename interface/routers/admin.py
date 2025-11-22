from __future__ import annotations

import json
import os
from typing import AsyncIterator

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from interface.api_shared import DB_PATH
from interface.dao import inserir_alertas, ensure_minimal_paciente_ficha

router = APIRouter(tags=["admin"])


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


def import_alerts_list(alerts: list[dict], db_path: str | None = None) -> int:
    """Helper to import a list of alert dicts into the DB via DAO."""
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
    """Admin endpoint to import alerts in bulk."""
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
        return {"ok": True, "inserted": inserted, "received": len(alerts)}
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_data", "message": str(e)})
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "import_failed", "message": str(e)})
