from __future__ import annotations

import asyncio
import os
from fastapi import APIRouter, Depends, status

from interface.api_shared import _check_api_rate_limit
from interface.dependencies import exigir_papel

from servicos.backup import BackupService, intervalo_de_backup_horas
from interface.api_shared import DB_PATH, erro_interno

# Endpoints administrativos de backup. Estavam totalmente abertos: um
# POST /admin/backup/cleanup?keep_days=0 anonimo apagava todos os backups.
# Depois passaram a exigir sessao — mas qualquer conta servia. Backup e
# operacao de administracao da instalacao, nao de uso clinico.
router = APIRouter(
    tags=["backup"],
    dependencies=[Depends(exigir_papel("admin")), Depends(_check_api_rate_limit)],
)

# Backup endpoints. O diretório de backup precisa estar dentro do volume
# persistente do Docker (ver docker-compose.yml) — um default relativo
# ("backups") se perderia a cada restart do container.
BACKUP_DIR = os.getenv("UPP_BACKUP_DIR", "backups")
backup_service = BackupService(DB_PATH, backup_dir=BACKUP_DIR)


def _sem_caminho(item: dict) -> dict:
    """Remove o caminho absoluto do arquivo antes de responder.

    `list_backups` e `verificar_todos` carregam `path` com o caminho real no
    disco do servidor. O `filename` e o unico identificador que o cliente
    precisa — todas as operacoes sao por nome, dentro do diretorio configurado.
    Devolver o caminho entrega a estrutura de diretorios do servidor ao
    navegador, exatamente o que `erro_interno` existe para evitar no resto da
    API. E admin, mas admin tambem nao precisa disso para operar.
    """
    return {chave: valor for chave, valor in item.items() if chave != "path"}


@router.post("/admin/backup/create", status_code=status.HTTP_200_OK)
async def create_backup() -> dict:
    """Cria um backup manual do banco de dados."""
    try:
        backup_path = await asyncio.to_thread(backup_service.create_backup)
        # So o nome: ver `_sem_caminho`.
        return {"ok": True, "filename": os.path.basename(str(backup_path))}
    except Exception as e:
        raise erro_interno("backup_failed", e) from e


@router.get("/admin/backup/list", status_code=status.HTTP_200_OK)
async def list_backups() -> dict:
    """Lista todos os backups disponíveis."""
    backups = await asyncio.to_thread(backup_service.list_backups)
    return {"backups": [_sem_caminho(b) for b in backups], "count": len(backups)}


@router.get("/admin/backup/status", status_code=status.HTTP_200_OK)
async def backup_status() -> dict:
    """Existe um backup recente que realmente restaura?

    Sem isto, a unica evidencia de que o backup funciona e uma linha de log que
    ninguem le. O agendador podia estar falhando havia semanas sem que nada na
    aplicacao ficasse diferente de uma instalacao saudavel — e a descoberta
    chegaria no dia da restauracao.
    """
    return await asyncio.to_thread(backup_service.estado, intervalo_de_backup_horas())


@router.post("/admin/backup/verify", status_code=status.HTTP_200_OK)
async def verify_backups() -> dict:
    """Abre cada backup e confere se da para restaurar a partir dele."""
    resultados = await asyncio.to_thread(backup_service.verificar_todos)
    return {
        "backups": [_sem_caminho(r) for r in resultados],
        "invalidos": sum(1 for r in resultados if not r["ok"]),
    }


@router.post("/admin/backup/cleanup", status_code=status.HTTP_200_OK)
async def cleanup_backups(keep_days: int = 7) -> dict:
    """Remove backups mais antigos que keep_days dias."""
    try:
        removed = await asyncio.to_thread(backup_service.cleanup_old_backups, keep_days)
        return {"ok": True, "removed_count": removed}
    except Exception as e:
        raise erro_interno("cleanup_failed", e, keep_days=keep_days) from e
