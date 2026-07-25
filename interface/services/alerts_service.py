"""Logica de negocio de alertas: listagem no formato do frontend,
reconhecimento/conclusao (individual e em lote) e exportacao. Extraido de
interface/routers/alerts.py para manter o router focado em parsing de
request/response HTTP (mesmo padrao ja aplicado em routers/ingestao.py).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Literal

import structlog

from interface.api_shared import DB_PATH, api_cache
from interface.dao import obter_ficha_paciente, selecionar_alertas_janela, selecionar_timeline, alterar_status_alerta, inserir_timeline_event
from interface.ws_manager_optimized import ws_manager_optimized
from servicos import metricas

logger = structlog.get_logger(__name__)

_RISK_MAP = {"alto": "high", "medio": "medium", "baixo": "low"}
_STATUS_MAP = {"aberto": "pending", "reconhecido": "acknowledged", "fechado": "completed"}

# Config por tipo de operação de alerta (usado por reconhecer/completar e
# pelas versões em lote, evitando duplicar a mesma lógica duas vezes).
_OPERACOES = {
    "acknowledge": {
        "novo_status": "reconhecido",
        "definir_fim": False,
        "timeline_tipo": "alert_ack",
        "timeline_desc": "Alerta reconhecido",
        "ws_status": "acknowledged",
        "metric_batch": "acknowledge",
        "metric_single": metricas.registrar_alert_acknowledged,
    },
    "complete": {
        "novo_status": "fechado",
        "definir_fim": True,
        "timeline_tipo": "alert_close",
        "timeline_desc": "Alerta fechado/completado",
        "ws_status": "completed",
        "metric_batch": "complete",
        "metric_single": metricas.registrar_alert_completed,
    },
}


async def listar_alertas_frontend(
    horas: int | None = 24,
    risk_level: str | None = None,
    status_filter: str | None = None,
    room: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Busca alertas e retorna no formato consumido pelo frontend React,
    com cache de 30s por combinação de filtros."""
    cache_key = f"alerts:{horas}:{risk_level}:{status_filter}:{room}:{limit}:{offset}"
    cached_result = await api_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    raw_alerts = selecionar_alertas_janela(DB_PATH, horas)
    results: list[dict] = []
    for a in raw_alerts:
        paciente_id = a.get("paciente_id")
        inicio = a.get("inicio")
        janela_min = int(a.get("janela_min") or 0)
        perfil = str(a.get("perfil") or "medio")
        status_raw = str(a.get("status") or "aberto")

        aid = f"{paciente_id}__{inicio}"

        ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=False)
        patient_name = ficha.get("nome") if ficha else paciente_id
        cama_id = (ficha.get("cama_id") if ficha else None) or ""
        room_val = cama_id
        bed = ""
        if cama_id and "/" in cama_id:
            parts = [p.strip() for p in cama_id.split("/")]
            room_val = parts[0]
            if len(parts) > 1:
                bed = parts[1]

        last_ts = None
        try:
            timeline = selecionar_timeline(DB_PATH, paciente_id=paciente_id, limit=50)
            for ev in sorted(timeline, key=lambda r: int(r.get("ts_ms", 0)), reverse=True):
                if ev.get("tipo") in {"alert_ack", "repositioned", "alert_close", "alert_open"}:
                    last_ts = ev.get("ts")
                    break
        except Exception:
            last_ts = None
        if last_ts is None:
            last_ts = inicio

        try:
            next_dt = datetime.fromisoformat(inicio[:19]) + timedelta(minutes=janela_min)
            next_iso = next_dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            next_iso = inicio

        risk_level_val = _RISK_MAP.get(perfil, "medium")
        status_val = _STATUS_MAP.get(status_raw, "pending")

        if risk_level and risk_level_val != risk_level:
            continue
        if status_filter and status_val != status_filter:
            continue
        if room and room.lower() not in room_val.lower():
            continue

        results.append(
            {
                "id": aid,
                "patientName": patient_name,
                "room": room_val,
                "bed": bed,
                "lastRepositioning": last_ts,
                "nextRepositioning": next_iso,
                "riskLevel": risk_level_val,
                "status": status_val,
            }
        )

    paginated_results = results[offset: offset + limit]
    await api_cache.set(cache_key, paginated_results, ttl_seconds=30)
    return paginated_results


def _montar_payload_broadcast(alert_id: str, paciente_id: str, ws_status: str) -> dict:
    """Monta a mensagem publicada no WS de alertas.

    Precisa carregar `severity`, `patient_id` e `alert_type` porque é contra
    esses campos que WebSocketFilter.matches() filtra (ws_manager_optimized.py).
    O payload só tinha type/alert_id/status/timestamp, então qualquer cliente
    conectado com ?severity=... ou ?patient_id=... nunca recebia nada.
    """
    severity = None
    alert_type = None
    try:
        _, inicio = alert_id.split("__", 1)
        for a in selecionar_alertas_janela(DB_PATH, horas=None):
            if a.get("paciente_id") == paciente_id and a.get("inicio") == inicio:
                severity = _RISK_MAP.get(str(a.get("perfil") or "").lower())
                alert_type = a.get("tipo")
                break
    except Exception:
        # Sem os metadados o cliente sem filtro ainda recebe a atualização;
        # não vale derrubar a operação por causa do enriquecimento.
        logger.warning("broadcast_metadata_falhou", alert_id=alert_id, exc_info=True)

    return {
        "type": "alert_update",
        "alert_id": alert_id,
        "status": ws_status,
        "patient_id": paciente_id,
        "severity": severity,
        "alert_type": alert_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _aplicar_operacao(alert_id: str, user: str, operacao: Literal["acknowledge", "complete"]) -> None:
    """Aplica reconhecer/completar a um único alerta: atualiza status,
    registra timeline, faz broadcast via WS e invalida o cache."""
    config = _OPERACOES[operacao]
    paciente_id, inicio = alert_id.split("__", 1)

    alterar_status_alerta(DB_PATH, paciente_id, inicio, config["novo_status"], config["definir_fim"])

    try:
        now = datetime.now(timezone.utc)
        ts_iso = now.isoformat()
        ts_ms = int(now.timestamp() * 1000)
        inserir_timeline_event(
            db_path=DB_PATH,
            paciente_id=paciente_id,
            ts=ts_iso,
            ts_ms=ts_ms,
            tipo=config["timeline_tipo"],
            descricao=f"{config['timeline_desc']} por {user}",
            meta={"alert_id": alert_id, "inicio": inicio, "action": operacao, "user": user},
        )
        logger.info(
            f"alert_{operacao}d" if operacao == "complete" else "alert_acknowledged",
            paciente_id=paciente_id,
            alert_id=alert_id,
            timeline_event=config["timeline_tipo"],
            user=user,
        )
    except Exception as exc:
        logger.warning(
            "timeline_event_failed",
            paciente_id=paciente_id,
            alert_id=alert_id,
            tipo=config["timeline_tipo"],
            error=str(exc),
        )

    await ws_manager_optimized.broadcast(
        _montar_payload_broadcast(alert_id, paciente_id, config["ws_status"])
    )
    await api_cache.clear()


async def reconhecer_alerta(alert_id: str, user: str) -> None:
    await _aplicar_operacao(alert_id, user, "acknowledge")


async def completar_alerta(alert_id: str, user: str) -> None:
    await _aplicar_operacao(alert_id, user, "complete")


async def processar_lote(alert_ids: List[str], user: str, operacao: Literal["acknowledge", "complete"]) -> dict:
    """Aplica reconhecer/completar a vários alertas em paralelo (thread pool
    para as operações de banco), com broadcast em background e métricas."""
    config = _OPERACOES[operacao]
    processed = 0
    failed = 0
    errors: List[dict] = []
    broadcast_tasks: List = []

    async def _process_alert(alert_id: str) -> tuple[bool, dict | None]:
        try:
            paciente_id, inicio = alert_id.split("__", 1)
            await asyncio.to_thread(
                alterar_status_alerta, DB_PATH, paciente_id, inicio, config["novo_status"], config["definir_fim"]
            )
            try:
                now = datetime.now(timezone.utc)
                ts_iso = now.isoformat()
                ts_ms = int(now.timestamp() * 1000)
                await asyncio.to_thread(
                    inserir_timeline_event,
                    DB_PATH,
                    paciente_id,
                    ts_iso,
                    ts_ms,
                    config["timeline_tipo"],
                    f"{config['timeline_desc']} em lote por {user}",
                    {"alert_id": alert_id, "inicio": inicio, "action": f"batch_{operacao}", "user": user},
                )
            except Exception as timeline_err:
                logger.warning(f"batch_{operacao}_timeline_failed", alert_id=alert_id, error=str(timeline_err))

            try:
                payload = await asyncio.to_thread(
                    _montar_payload_broadcast, alert_id, paciente_id, config["ws_status"]
                )
                task = asyncio.create_task(ws_manager_optimized.broadcast(payload))
                broadcast_tasks.append(task)
            except Exception as ws_err:
                logger.warning(f"batch_{operacao}_broadcast_queued_failed", error=str(ws_err))

            return True, None
        except Exception as exc:
            return False, {"alert_id": alert_id, "error": str(exc)}

    tasks = [_process_alert(aid) for aid in alert_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            failed += 1
            errors.append({"error": str(result)})
        elif result[0]:
            processed += 1
        else:
            failed += 1
            if result[1]:
                errors.append(result[1])

    async def _log_broadcast_results() -> None:
        try:
            await asyncio.gather(*broadcast_tasks, return_exceptions=True)
        except Exception:
            pass

    try:
        asyncio.create_task(_log_broadcast_results())
    except Exception:
        pass

    await api_cache.clear()

    metricas.registrar_batch_operation(config["metric_batch"], processed)
    for _ in range(processed):
        config["metric_single"]()

    return {"ok": True, "processed": processed, "failed": failed, "errors": errors}


def parsear_data_export(valor: str | None, nome_campo: str) -> datetime | None:
    """Faz parse de uma data YYYY-MM-DD usada nos filtros de export.
    Levanta ValueError com mensagem amigável se o formato for inválido."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        raise ValueError(f"{nome_campo} inválido. Use YYYY-MM-DD")
