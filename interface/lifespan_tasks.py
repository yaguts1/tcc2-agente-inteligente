"""Tarefas de background iniciadas/paradas junto com o lifespan da app FastAPI.

Deployment de instancia unica (ver docs de deploy) — estas tasks nao usam
lock distribuido; rodar 2+ replicas duplicaria o processamento de eventos
de device e os backups.
"""
from __future__ import annotations

import asyncio
import os

import structlog
from fastapi import FastAPI

from interface.api import reconcile_device_events
from servicos.backup import scheduled_backup_task

logger = structlog.get_logger(__name__)


def start_reconciler_task(app: FastAPI) -> asyncio.Task:
    """Inicia o loop que reconcilia device_events pendentes periodicamente."""
    try:
        interval = max(1, int(os.getenv("DEVICE_RECONCILE_INTERVAL", "30")))
    except Exception:
        interval = 30

    async def _loop() -> None:
        logger.info("reconciler_started", interval=interval)
        while True:
            try:
                result = await reconcile_device_events(None, 100)
                if result and (result.get("processed", 0) or result.get("skipped", 0)):
                    logger.info("reconciler_cycle", processed=result.get("processed"), skipped=result.get("skipped"))
            except asyncio.CancelledError:
                logger.info("reconciler_cancelled")
                raise
            except Exception as exc:
                logger.exception("reconciler_error", motivo=str(exc))
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("reconciler_sleep_cancelled")
                raise

    task = asyncio.create_task(_loop(), name="device_reconciler")
    app.state._reconcile_task = task
    return task


async def stop_reconciler_task(app: FastAPI) -> None:
    task = getattr(app.state, "_reconcile_task", None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("reconciler_stopped")


def start_backup_task(app: FastAPI, db_path: str, backup_dir: str) -> asyncio.Task:
    """Inicia o loop que cria e limpa backups do banco periodicamente."""
    try:
        interval_hours = max(1, int(os.getenv("BACKUP_INTERVAL_HOURS", "24")))
    except Exception:
        interval_hours = 24

    async def _loop() -> None:
        logger.info("backup_scheduler_started", interval_hours=interval_hours, backup_dir=backup_dir)
        while True:
            try:
                await asyncio.sleep(interval_hours * 3600)
            except asyncio.CancelledError:
                logger.info("backup_scheduler_sleep_cancelled")
                raise
            try:
                await asyncio.to_thread(scheduled_backup_task, db_path, backup_dir, 7)
                logger.info("backup_scheduler_cycle_done")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("backup_scheduler_error", motivo=str(exc))

    task = asyncio.create_task(_loop(), name="backup_scheduler")
    app.state._backup_task = task
    return task


async def stop_backup_task(app: FastAPI) -> None:
    task = getattr(app.state, "_backup_task", None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("backup_scheduler_stopped")
