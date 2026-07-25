from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from interface.dependencies import get_current_user

from interface.api_shared import DB_PATH, erro_interno
from interface.dao import (
    registrar_device,
    listar_devices,
    listar_device_events,
    obter_ficha_por_cama,
)
from interface.schemas import DeviceRegisterRequest

# Painel de dispositivos (listagem, eventos brutos, estatisticas): consumido
# pela tela de administracao, nao pelo firmware — o ESP32 se registra pelo
# proprio fluxo de ingestao.
router = APIRouter(tags=["devices"], dependencies=[Depends(get_current_user)])


@router.post("/devices/register", status_code=status.HTTP_201_CREATED)
def api_register_device(payload: DeviceRegisterRequest) -> dict:
    try:
        registrar_device(DB_PATH, payload.device_id, payload.meta)
    except Exception as exc:
        raise erro_interno("device_error", exc) from exc
    return {"device_id": payload.device_id}


@router.get("/devices", status_code=status.HTTP_200_OK)
def api_list_devices() -> list[dict]:
    return listar_devices(DB_PATH)


@router.get("/device_events", status_code=status.HTTP_200_OK)
def api_list_device_events(device_id: str | None = None, limit: int = 100) -> list[dict]:
    return listar_device_events(DB_PATH, device_id=device_id, limit=limit)


@router.get("/device_events/stats", status_code=status.HTTP_200_OK)
def api_device_events_stats() -> dict:
    """Return statistics about orphan device events grouped by bed (cama_id).
    
    Returns:
    {
        "total_orphans": int,
        "beds": [
            {
                "cama_id": str,
                "count": int,
                "first_event": str (ISO timestamp),
                "last_event": str (ISO timestamp),
                "current_patient": {
                    "id": str,
                    "name": str
                } | null
            }
        ]
    }
    """
    events = listar_device_events(DB_PATH, device_id=None, limit=10000)
    
    # Group by cama_id
    bed_stats: dict[str, dict] = {}
    
    for ev in events:
        payload = ev.get("payload") or {}
        cama_id = payload.get("cama_id")
        
        if not cama_id:
            continue
            
        if cama_id not in bed_stats:
            bed_stats[cama_id] = {
                "cama_id": cama_id,
                "count": 0,
                "first_event": None,
                "last_event": None,
                "events": []
            }
        
        bed_stats[cama_id]["count"] += 1
        bed_stats[cama_id]["events"].append(ev.get("ts"))
    
    # Process timestamps and find current patients
    beds_list = []
    for cama_id, stats in bed_stats.items():
        timestamps = sorted([t for t in stats["events"] if t])
        
        result = {
            "cama_id": cama_id,
            "count": stats["count"],
            "first_event": timestamps[0] if timestamps else None,
            "last_event": timestamps[-1] if timestamps else None,
            "current_patient": None
        }
        
        # Try to find current patient in this bed
        try:
            paciente = obter_ficha_por_cama(DB_PATH, cama_id, incluir_rotinas=False)
            if paciente:
                result["current_patient"] = {
                    "id": paciente.get("paciente_id"),
                    "name": paciente.get("nome")
                }
        except Exception:
            pass
        
        beds_list.append(result)
    
    # Sort by count (descending)
    beds_list.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "total_orphans": len(events),
        "beds": beds_list
    }
