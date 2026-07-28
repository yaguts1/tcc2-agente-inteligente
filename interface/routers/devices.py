from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from interface.dependencies import exigir_papel, get_current_user

from interface.api_shared import DB_PATH, _check_api_rate_limit, erro_interno
from interface.dao import (
    registrar_device,
    listar_devices,
    listar_device_events,
    obter_ficha_por_cama,
)
from interface.repositories.devices import contar_device_events
from interface.schemas import DeviceRegisterRequest

logger = structlog.get_logger(__name__)

# Painel de dispositivos (listagem, eventos brutos, estatisticas): consumido
# pela tela de administracao, nao pelo firmware — o ESP32 se registra pelo
# proprio fluxo de ingestao.
router = APIRouter(
    tags=["devices"],
    dependencies=[Depends(get_current_user), Depends(_check_api_rate_limit)],
)


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


# Teto da amostra usada para agrupar por leito. O TOTAL nao depende dele (vem
# de `contar_device_events`), mas o agrupamento sim — por isso a resposta diz
# quando a amostra foi cortada, em vez de apresentar parciais como completos.
LIMITE_AMOSTRA_STATS = 10000


@router.get("/device_events/stats", status_code=status.HTTP_200_OK)
def api_device_events_stats() -> dict:
    """Estatisticas dos eventos orfaos, agrupadas por leito (cama_id).

    Returns:
    {
        "total_orphans": int,       # TODOS os orfaos pendentes
        "orfaos_com_leito": int,    # os que a reconciliacao por leito alcanca
        "orfaos_sem_leito": int,    # os que nenhum botao desta tela resolve
        "amostra_truncada": bool,
        "beds": [ { cama_id, count, first_event, last_event, current_patient } ]
    }

    `total_orphans` era `len(events)` — a contagem da amostra JA limitada, e
    incluindo eventos cujo payload nao tem `cama_id`. Duas consequencias na
    tela de admin, que exibe esse numero como "N eventos aguardando
    reconciliacao":

      * eventos sem `cama_id` entravam na conta e nao aparecem em leito nenhum,
        entao o operador reconciliava TODOS os leitos e o numero nao zerava,
        sem nada explicando por que;
      * acima do teto da amostra o total parava de crescer — justo num painel
        cuja funcao e diagnosticar acumulo.
    """
    total_pendentes = contar_device_events(DB_PATH, device_id=None)
    events = listar_device_events(DB_PATH, device_id=None, limit=LIMITE_AMOSTRA_STATS)

    # Group by cama_id
    bed_stats: dict[str, dict] = {}
    sem_leito = 0

    for ev in events:
        payload = ev.get("payload") or {}
        cama_id = payload.get("cama_id")

        if not cama_id:
            # Sem leito no payload nao ha o que reconciliar por leito: estes
            # dependem da reconciliacao por device/tempo.
            sem_leito += 1
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
            # `pass` calado aqui induzia o operador ao erro: sem paciente
            # resolvido, a tela mostra "Leito vazio" e instrui a "cadastrar um
            # paciente neste leito" — conselho errado quando o paciente existe
            # e a consulta e que falhou. Continua sem derrubar o painel, mas
            # deixa rastro.
            logger.warning("ficha_por_cama_falhou", cama_id=cama_id, exc_info=True)

        beds_list.append(result)

    # Sort by count (descending)
    beds_list.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_orphans": total_pendentes,
        "orfaos_com_leito": sum(b["count"] for b in beds_list),
        "orfaos_sem_leito": sem_leito,
        # Acima do teto o agrupamento por leito e parcial. Dizer isso e o que
        # separa "estes sao todos os leitos" de "estes sao os leitos que
        # couberam na amostra".
        "amostra_truncada": total_pendentes > len(events),
        "beds": beds_list
    }


# ---------------------------------------------------------------------------
# Credencial por dispositivo
# ---------------------------------------------------------------------------
#
# Emitir e revogar credencial e operacao administrativa, e por isso exige
# `admin` alem da sessao que o router inteiro ja pede: quem opera a ala nao
# precisa poder criar credencial que fala em nome de um leito.


@router.get(
    "/devices/tokens",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(exigir_papel("admin"))],
)
def listar_tokens_de_dispositivo() -> list[dict]:
    """Estado das credenciais. Nunca expoe hash nem texto puro."""
    from interface.repositories.device_tokens import listar

    return listar(DB_PATH)


@router.post(
    "/devices/{device_id}/token",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(exigir_papel("admin"))],
)
def emitir_token_de_dispositivo(device_id: str, admin: str = Depends(get_current_user)) -> dict:
    """Gera a credencial do dispositivo e devolve o texto puro UMA VEZ.

    O servidor guarda so o hash: nao ha endpoint para reler o token depois, e
    isso e a propriedade, nao uma limitacao. Perdeu, emite outro — barato, e o
    aparelho que estiver com o antigo para de ser aceito na hora, que e o
    comportamento desejado quando alguem perde a credencial de vista.

    Emitir de novo ROTACIONA: substitui o token anterior. O `config.h` do
    aparelho precisa ser atualizado, senao ele passa a receber 401 — que o
    firmware trata como falha TRANSIENTE e reenvia, entao a amostra nao se
    perde enquanto o aparelho nao e reflasheado.
    """
    from interface.repositories.device_tokens import emitir

    try:
        token = emitir(DB_PATH, device_id, criado_por=admin)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "device_invalido", "message": str(exc)},
        ) from exc

    return {
        "device_id": device_id,
        "token": token,
        "aviso": (
            "Guarde agora: o servidor nao consegue mostrar este token de novo."
            " Grave em DEVICE_TOKEN no config.h deste aparelho."
        ),
    }


@router.delete(
    "/devices/{device_id}/token",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(exigir_papel("admin"))],
)
def revogar_token_de_dispositivo(device_id: str, admin: str = Depends(get_current_user)) -> dict:
    """Invalida a credencial do dispositivo imediatamente.

    E a operacao que nao existia: com um segredo unico para a frota, revogar
    exigia trocar a variavel de ambiente e reflashear TODOS os aparelhos, o que
    na pratica significava nunca revogar.

    O dispositivo revogado NAO volta a ser aceito pelo token global: ter tido
    credencial propria e o que marca o aparelho como migrado, e o proposito da
    revogacao e justamente cortar o acesso daquele aparelho.
    """
    from interface.repositories.device_tokens import revogar

    if not revogar(DB_PATH, device_id, revogado_por=admin):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "token_nao_encontrado",
                "message": "Dispositivo nao tem credencial ativa.",
            },
        )
    return {"ok": True, "device_id": device_id, "revogado_por": admin}
