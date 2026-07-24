from __future__ import annotations

import asyncio
import os
from fastapi import APIRouter, HTTPException, status

from servicos.backup import BackupService
from interface.api_shared import DB_PATH

router = APIRouter(tags=["backup"])

# Backup endpoints. O diretório de backup precisa estar dentro do volume
# persistente do Docker (ver docker-compose.yml) — um default relativo
# ("backups") se perderia a cada restart do container.
BACKUP_DIR = os.getenv("UPP_BACKUP_DIR", "backups")
backup_service = BackupService(DB_PATH, backup_dir=BACKUP_DIR)


@router.post("/admin/backup/create", status_code=status.HTTP_200_OK)
async def create_backup() -> dict:
    """Cria um backup manual do banco de dados."""
    try:
        backup_path = await asyncio.to_thread(backup_service.create_backup)
        return {"ok": True, "backup_path": backup_path}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "backup_failed", "message": str(e)}
        )


@router.get("/admin/backup/list", status_code=status.HTTP_200_OK)
async def list_backups() -> dict:
    """Lista todos os backups disponíveis."""
    backups = await asyncio.to_thread(backup_service.list_backups)
    return {"backups": backups, "count": len(backups)}


@router.post("/admin/backup/cleanup", status_code=status.HTTP_200_OK)
async def cleanup_backups(keep_days: int = 7) -> dict:
    """Remove backups mais antigos que keep_days dias."""
    try:
        removed = await asyncio.to_thread(backup_service.cleanup_old_backups, keep_days)
        return {"ok": True, "removed_count": removed}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "cleanup_failed", "message": str(e)}
        )
