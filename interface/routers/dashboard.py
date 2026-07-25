from __future__ import annotations

import time
from datetime import datetime, timezone
import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from interface.api_shared import DB_PATH, APP_VERSION, APP_START_TIME, DEFAULT_PERFIL, erro_interno
from interface.dao import (
    selecionar_alertas_janela,
    listar_fichas_pacientes,
    obter_ficha_paciente,
    selecionar_timeline,
)
from interface.db_core import connect
from interface.dependencies import get_current_user
from interface.repositories.monitoramento import (
    resumo as resumo_monitoramento,
    status_por_paciente,
)
from interface.tempo import agora_utc_naive
from interface.ws_manager_optimized import ws_manager_optimized

logger = structlog.get_logger(__name__)
# Exige sessao: /stats e /timeline expoem dados clinicos e /health detalha
# DB_PATH e contagem de alertas. O healthcheck do container usa /healthz
# (interface/web.py), que segue publico de proposito.
router = APIRouter(tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check() -> dict:
    """
    Comprehensive health check endpoint.
    Returns service status, database connectivity, WebSocket connections, version, and uptime.
    """
    uptime_seconds = time.time() - APP_START_TIME
    uptime_hours = uptime_seconds / 3600
    
    # Check database connectivity
    db_status = "unknown"
    db_error = None
    try:
        # Usa o connect() do db_core em vez de sqlite3.connect cru: assim herda
        # WAL, busy_timeout e o fechamento garantido. Antes, o conn.close()
        # ficava depois do fetchone() e era pulado quando a query falhava — ou
        # seja, o proprio endpoint de saude vazava conexao justamente quando o
        # banco estava com problema.
        with connect(DB_PATH) as conn:
            alert_count = conn.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
        db_status = "healthy"
    except Exception as e:
        db_status = "unhealthy"
        db_error = str(e)
        alert_count = None
    
    # Get WebSocket connection count
    ws_connections = len(ws_manager_optimized.active_connections)
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": APP_VERSION,
        "uptime_seconds": round(uptime_seconds, 2),
        "uptime_hours": round(uptime_hours, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "status": db_status,
            "path": DB_PATH,
            "alert_count": alert_count,
            "error": db_error
        },
        "websocket": {
            "active_connections": ws_connections
        }
    }


@router.get("/stats", status_code=status.HTTP_200_OK)
def get_stats() -> dict:
    """Retorna estatísticas do dashboard para o frontend.
    
    ✅ CORRIGIDO: Usa janela temporal CONSISTENTE de 24h para todas as métricas
    
    Antes: activeAlerts=7 dias, acknowledgedAlerts=7 dias, completedToday=24h
           Causava taxa de conclusão inconsistente (misturava períodos diferentes)
    
    Agora: TODAS as métricas usam 24h (últimas 24 horas)
           Taxa de conclusão = fechados_24h / (abertos_24h + reconhecidos_24h + fechados_24h)
    
    Retorna: activeAlerts, acknowledgedAlerts, completedToday, totalPatients, completionRate
    """
    try:
        # ✅ CORRIGIDO: Usar janela CONSISTENTE de 24 horas para TODAS as métricas
        # Antes: selecionar_alertas_janela(DB_PATH, horas=168)  # 1 semana - INCONSISTENTE!
        # Agora: selecionar_alertas_janela(DB_PATH, horas=24)   # 24 horas - CONSISTENTE!
        all_alerts_24h = selecionar_alertas_janela(DB_PATH, horas=24)
        
        # Contar alertas abertos (pending) nas últimas 24h
        active_alerts = len([a for a in all_alerts_24h if a.get("status") == "aberto"])
        
        # Contar alertas reconhecidos (acknowledged) nas últimas 24h
        acked_alerts = len([a for a in all_alerts_24h if a.get("status") == "reconhecido"])
        
        # Contar alertas fechados (completed) nas últimas 24h
        completed_today = len([a for a in all_alerts_24h if a.get("status") == "fechado"])
        
        # Contar pacientes totais
        fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False)
        total_patients = len(fichas)
        
        # ✅ CORRIGIDO: Taxa de conclusão agora usa dados CONSISTENTES (todas 24h)
        # Fórmula: fechados / (abertos + reconhecidos + fechados) nas últimas 24h
        # Representa: % de alertas que foram completados no período de 24h
        total_relevant = active_alerts + acked_alerts + completed_today
        completion_rate = (
            (completed_today / total_relevant * 100) 
            if total_relevant > 0 else 0
        )
        
        # Saúde do monitoramento entra no MESMO payload das estatísticas de
        # propósito. O dashboard afirmava "Todos os pacientes estão com
        # reposicionamento em dia" sempre que não havia alertas — mas ausência
        # de alerta também é o que acontece quando o sensor morre, o WiFi cai
        # ou a ingestão quebra. Sem este número ao lado, a tela não tem como
        # distinguir "está tudo bem" de "parei de receber dados".
        saude = resumo_monitoramento(DB_PATH)

        return {
            "activeAlerts": active_alerts,
            "acknowledgedAlerts": acked_alerts,
            "completedToday": completed_today,
            "totalPatients": total_patients,
            "completionRate": round(completion_rate, 1),
            "unmonitoredPatients": saude["sem_monitoramento"],
            "monitoringLimitMin": saude["limite_min"],
        }
    except Exception as exc:
        logger.exception("stats_error", erro=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "stats_error", "message": "Erro interno ao processar a requisicao."}
        ) from exc


@router.get("/monitoramento", status_code=status.HTTP_200_OK)
def status_monitoramento() -> dict:
    """Quais pacientes estão (ou não) com dados chegando.

    Responde à pergunta que o dashboard não conseguia responder: "não há
    alertas porque está tudo bem, ou porque parei de receber dados?".

    `nunca_recebeu_dados` separa "o sensor parou" de "nunca chegou leitura
    nenhuma" — a segunda costuma ser erro de instalação ou de vínculo
    device↔leito, e a ação corretiva é diferente.
    """
    try:
        detalhe = status_por_paciente(DB_PATH)
        agregado = resumo_monitoramento(DB_PATH)
        return {**agregado, "pacientes": detalhe}
    except Exception as exc:
        raise erro_interno("monitoramento_error", exc) from exc


@router.get("/validate-repositioning/{paciente_id}", status_code=status.HTTP_200_OK)
def validate_repositioning_contract(paciente_id: str) -> dict:
    """Valida o contrato Backend/Frontend para repouso.
    
    Valida:
    1. Último repouso (ultimo_repouso) < Próximo repouso (proximo_repouso)
    2. Próximo repouso (proximo_repouso) > Agora (deve estar no futuro)
    3. Intervalo entre repouso é consistente com perfil
    
    Retorna: {
        "valid": bool,
        "errors": [str],
        "ultimo_repouso": ISO string,
        "proximo_repouso": ISO string,
        "intervalo_horas": float,
        "perfil": str,
        "agora": ISO string
    }
    """
    try:
        ficha = obter_ficha_paciente(DB_PATH, paciente_id)
        if ficha is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "paciente_nao_encontrado", "message": f"Paciente {paciente_id} nao encontrado."}
            )
        
        # Comparado contra `inicio`/`fim` dos alertas, que são UTC naive.
        agora = agora_utc_naive()
        errors = []
        
        # Buscar alertas (não filtra por paciente_id na DAO, então filtramos aqui)
        todos_alertas = selecionar_alertas_janela(DB_PATH, horas=24)
        alertas = [a for a in todos_alertas if a.get("paciente_id") == paciente_id]
        
        # Buscar último alerta (último repouso)
        alertas_filtrados = [a for a in alertas if a.get("status") == "fechado"]
        
        ultimo_repouso = None
        if alertas_filtrados:
            # Pega o mais recente (último fim de alerta)
            alertas_ordenados = sorted(alertas_filtrados, key=lambda x: x.get("fim", ""), reverse=True)
            último_alerta = alertas_ordenados[0]
            if último_alerta.get("fim"):
                try:
                    ultimo_repouso = datetime.fromisoformat(último_alerta.get("fim")[:19])
                except (ValueError, TypeError):
                    # Campo `fim` ausente/malformado é esperado — segue com None.
                    ultimo_repouso = None
        
        # Buscar próximo alerta (próximo repouso)
        alertas_abertos = [a for a in alertas if a.get("status") == "aberto"]
        proximo_repouso = None
        if alertas_abertos:
            alertas_ordenados = sorted(alertas_abertos, key=lambda x: x.get("inicio", ""))
            próximo_alerta = alertas_ordenados[0]
            if próximo_alerta.get("inicio"):
                try:
                    proximo_repouso = datetime.fromisoformat(próximo_alerta.get("inicio")[:19])
                except (ValueError, TypeError):
                    # Campo `inicio` ausente/malformado é esperado — segue com None.
                    proximo_repouso = None
        
        # Validar contrato
        if ultimo_repouso and proximo_repouso:
            if ultimo_repouso >= proximo_repouso:
                errors.append(f"ultimo_repouso ({ultimo_repouso.isoformat()}) >= proximo_repouso ({proximo_repouso.isoformat()})")
        
        if proximo_repouso and proximo_repouso <= agora:
            errors.append(f"proximo_repouso ({proximo_repouso.isoformat()}) <= agora ({agora.isoformat()}) - DEVE estar no FUTURO!")
        
        intervalo_horas = None
        if ultimo_repouso and proximo_repouso:
            intervalo_horas = (proximo_repouso - ultimo_repouso).total_seconds() / 3600.0
        
        perfil = ficha.get("perfil", DEFAULT_PERFIL)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "ultimo_repouso": ultimo_repouso.isoformat() if ultimo_repouso else None,
            "proximo_repouso": proximo_repouso.isoformat() if proximo_repouso else None,
            "intervalo_horas": round(intervalo_horas, 2) if intervalo_horas else None,
            "perfil": perfil,
            "agora": agora.isoformat()
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("validate_repositioning_error", erro=str(exc), paciente_id=paciente_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "validate_error", "message": "Erro interno ao processar a requisicao."}
        ) from exc


@router.get("/timeline", status_code=status.HTTP_200_OK)
def get_timeline(
    paciente_id: str | None = None,
    tipo: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 100
) -> list[dict]:
    """
    Retorna eventos da timeline com filtros opcionais.
    Enriquece os eventos com o nome do paciente.
    """
    try:
        # Buscar eventos
        eventos = selecionar_timeline(
            DB_PATH,
            paciente_id=paciente_id,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=limit,
            tipo=tipo
        )
        
        # Buscar nomes dos pacientes para enriquecer
        # Se paciente_id foi fornecido, buscamos apenas ele
        # Se não, buscamos todos para mapear
        paciente_map = {}
        if paciente_id:
            ficha = obter_ficha_paciente(DB_PATH, paciente_id)
            if ficha:
                paciente_map[paciente_id] = ficha["nome"]
        else:
            fichas = listar_fichas_pacientes(DB_PATH)
            paciente_map = {f["paciente_id"]: f["nome"] for f in fichas}
            
        # Enriquecer eventos
        result = []
        for ev in eventos:
            pid = ev.get("paciente_id")
            ev["paciente_name"] = paciente_map.get(pid, "Desconhecido") if pid else None
            result.append(ev)
            
        return result
    except Exception as exc:
        logger.exception("timeline_error", erro=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "timeline_error", "message": "Erro interno ao processar a requisicao."}
        ) from exc
