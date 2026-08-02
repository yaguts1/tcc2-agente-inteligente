from __future__ import annotations

import time
from datetime import datetime, UTC
import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from interface.api_shared import (
    DB_PATH,
    APP_VERSION,
    APP_START_TIME,
    DEFAULT_PERFIL,
    _check_api_rate_limit,
    erro_interno,
)
from interface.dao import (
    selecionar_alertas_janela,
    listar_fichas_pacientes,
    obter_ficha_paciente,
    selecionar_timeline,
)
from interface.db_core import connect
from interface.dependencies import escopo_de_unidades, get_current_user
from interface.repositories.alertas import ORIGEM_EQUIPE, ORIGEM_SENSOR
from interface.schemas import DashboardStatsResponse, MonitoramentoResponse
from interface.repositories.monitoramento import (
    resumo as resumo_monitoramento,
    status_por_paciente,
)
from interface.tempo import agora_utc_naive, para_iso_utc
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
        "timestamp": datetime.now(UTC).isoformat(),
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


# `/health` fica FORA do rate limit de proposito (ver `_check_api_rate_limit`):
# healthcheck limitado faz o monitoramento derrubar o servico que ele vigia.
@router.get("/stats", response_model=DashboardStatsResponse, status_code=status.HTTP_200_OK)
def get_stats(
    _: None = Depends(_check_api_rate_limit),
    unidades: set[int] | None = Depends(escopo_de_unidades),
) -> dict:
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

        # Escopo por unidade. Sem ele `/stats` MEDIA as duas alas num
        # `completionRate` so, que para efeito de accountability e pior que nao
        # ter numero nenhum: nem a ala boa nem a ruim se reconhecem no valor.
        #
        # As fichas visiveis sao o porteiro, o mesmo criterio da listagem de
        # alertas — duas regras de visibilidade divergentes sobre o mesmo dado
        # seria a forma mais silenciosa de vazar.
        fichas = listar_fichas_pacientes(DB_PATH, incluir_rotinas=False, unidades=unidades)
        if unidades is not None:
            visiveis = {str(f.get("paciente_id")) for f in fichas}
            all_alerts_24h = [
                a for a in all_alerts_24h if str(a.get("paciente_id")) in visiveis
            ]
        
        # Contar alertas abertos (pending) nas últimas 24h
        active_alerts = len([a for a in all_alerts_24h if a.get("status") == "aberto"])
        
        # Contar alertas reconhecidos (acknowledged) nas últimas 24h
        acked_alerts = len([a for a in all_alerts_24h if a.get("status") == "reconhecido"])
        
        # Contar alertas fechados (completed) nas últimas 24h
        fechados = [a for a in all_alerts_24h if a.get("status") == "fechado"]
        completed_today = len(fechados)

        # Fechado pela EQUIPE vs. fechado sozinho pelo paciente.
        #
        # Os dois viravam a mesma linha e entravam no mesmo numero, entao a KPI
        # de capa media adesao da enfermagem somada a mobilidade do paciente: um
        # paciente que rola sozinho gerava um "concluido" sem humano nenhum.
        # Para o TCC isso contamina a variavel de desfecho primaria.
        #
        # Linhas anteriores a migrations/0007 tem `origem_fechamento` NULL —
        # nao da para saber retroativamente qual caminho fechou cada uma, e
        # chutar 'equipe' inventaria adesao. Ficam de fora das duas contagens e
        # aparecem em `completedUnknownOrigin`, para a tela poder dizer que o
        # numero e parcial em vez de mentir por omissao.
        completed_by_team = len([a for a in fechados if a.get("origem_fechamento") == ORIGEM_EQUIPE])
        completed_by_sensor = len([a for a in fechados if a.get("origem_fechamento") == ORIGEM_SENSOR])
        completed_unknown = completed_today - completed_by_team - completed_by_sensor

        # Pacientes internados nas unidades visiveis (a lista ja foi carregada
        # acima para servir de porteiro dos alertas).
        total_patients = len(fichas)

        # ✅ CORRIGIDO: Taxa de conclusão agora usa dados CONSISTENTES (todas 24h)
        # Fórmula: fechados / (abertos + reconhecidos + fechados) nas últimas 24h
        # Representa: % de alertas que foram completados no período de 24h
        total_relevant = active_alerts + acked_alerts + completed_today
        completion_rate = (
            (completed_today / total_relevant * 100)
            if total_relevant > 0 else 0
        )

        # Tempo ate reconhecimento: quanto a ala demora para VER o alerta.
        #
        # Nao era derivavel do modelo. `duracao_min` e `fim - inicio`, ou seja
        # deteccao -> resolucao; o intervalo que diz se a ala e RESPONSIVA
        # (deteccao -> alguem viu) so existia como prosa na timeline, e
        # portanto nao era consultavel nem agregavel.
        #
        # Mediana, e nao media: um unico alerta esquecido a noite inteira
        # levaria a media para as alturas e esconderia que o resto da ala
        # responde em minutos. A pergunta e "como e o plantao tipico", e para
        # isso a mediana e a resposta honesta.
        tempos_ate_ack = []
        for a in all_alerts_24h:
            reconhecido_em = a.get("reconhecido_em")
            if not reconhecido_em:
                continue
            try:
                inicio_dt = datetime.fromisoformat(str(a["inicio"])[:19])
                ack_dt = datetime.fromisoformat(str(reconhecido_em)[:19])
            except (ValueError, TypeError, KeyError):
                continue
            minutos = (ack_dt - inicio_dt).total_seconds() / 60.0
            if minutos >= 0:
                tempos_ate_ack.append(minutos)

        tempos_ate_ack.sort()
        if tempos_ate_ack:
            meio = len(tempos_ate_ack) // 2
            mediana_ack = (
                tempos_ate_ack[meio]
                if len(tempos_ate_ack) % 2
                else (tempos_ate_ack[meio - 1] + tempos_ate_ack[meio]) / 2
            )
        else:
            # `None`, e nao 0: zero minutos de resposta seria um numero
            # excelente, e "ninguem reconheceu nada" e o oposto disso.
            mediana_ack = None

        # A taxa que responde "a equipe esta virando os pacientes?" — a pergunta
        # que a coordenacao faz. `completionRate` continua existindo porque a
        # tela ja o consome, mas ele responde outra coisa: "quantos alertas
        # deixaram de estar abertos", por qualquer motivo.
        team_completion_rate = (
            (completed_by_team / total_relevant * 100)
            if total_relevant > 0 else 0
        )

        # Saúde do monitoramento entra no MESMO payload das estatísticas de
        # propósito. O dashboard afirmava "Todos os pacientes estão com
        # reposicionamento em dia" sempre que não havia alertas — mas ausência
        # de alerta também é o que acontece quando o sensor morre, o WiFi cai
        # ou a ingestão quebra. Sem este número ao lado, a tela não tem como
        # distinguir "está tudo bem" de "parei de receber dados".
        saude = resumo_monitoramento(DB_PATH, unidades=unidades)

        # Braden vencido entra no MESMO payload, ao lado do watchdog de sensor,
        # e pelo mesmo motivo: sao as duas formas de o sistema estar cego.
        #
        # O watchdog cobre "parei de receber dados"; este cobre "estou vigiando
        # com uma classificacao de risco que pode nao valer mais". Um paciente
        # que piorou e cuja janela continua a de 120 min esta sendo monitorado
        # com o protocolo errado — e nada na tela diria isso.
        from interface.repositories.braden import reavaliacoes_pendentes

        braden = reavaliacoes_pendentes(DB_PATH, unidades=unidades)

        return {
            "activeAlerts": active_alerts,
            "acknowledgedAlerts": acked_alerts,
            "completedToday": completed_today,
            "completedByTeam": completed_by_team,
            "completedBySensor": completed_by_sensor,
            "completedUnknownOrigin": completed_unknown,
            "totalPatients": total_patients,
            "completionRate": round(completion_rate, 1),
            "teamCompletionRate": round(team_completion_rate, 1),
            "medianAckMinutes": None if mediana_ack is None else round(mediana_ack, 1),
            "acknowledgedCount": len(tempos_ate_ack),
            "unmonitoredPatients": saude["sem_monitoramento"],
            "monitoringLimitMin": saude["limite_min"],
            "bradenPendentes": braden["pendentes"],
            "bradenNuncaAvaliado": len(braden["nunca_avaliado"]),
            "bradenLimiteHoras": braden["limite_horas"],
        }
    except Exception as exc:
        logger.exception("stats_error", erro=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "stats_error", "message": "Erro interno ao processar a requisicao."}
        ) from exc


@router.get(
    "/monitoramento",
    response_model=MonitoramentoResponse,
    status_code=status.HTTP_200_OK,
)
def status_monitoramento(
    _: None = Depends(_check_api_rate_limit),
    unidades: set[int] | None = Depends(escopo_de_unidades),
) -> dict:
    """Quais pacientes estão (ou não) com dados chegando.

    Responde à pergunta que o dashboard não conseguia responder: "não há
    alertas porque está tudo bem, ou porque parei de receber dados?".

    `nunca_recebeu_dados` separa "o sensor parou" de "nunca chegou leitura
    nenhuma" — a segunda costuma ser erro de instalação ou de vínculo
    device↔leito, e a ação corretiva é diferente.
    """
    try:
        detalhe = status_por_paciente(DB_PATH, unidades=unidades)
        agregado = resumo_monitoramento(DB_PATH, unidades=unidades)
        return {**agregado, "pacientes": detalhe}
    except Exception as exc:
        raise erro_interno("monitoramento_error", exc) from exc


@router.get("/validate-repositioning/{paciente_id}", status_code=status.HTTP_200_OK)
def validate_repositioning_contract(
    paciente_id: str, _: None = Depends(_check_api_rate_limit)
) -> dict:
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
    limit: int = 100,
    _: None = Depends(_check_api_rate_limit),
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
            # `ts` sai do banco em UTC naive. Sem offset explícito o browser o
            # lê como hora LOCAL e a linha do tempo do paciente aparece 3h
            # adiantada para quem está no Brasil.
            ev["ts"] = para_iso_utc(ev.get("ts"))
            result.append(ev)

        return result
    except Exception as exc:
        logger.exception("timeline_error", erro=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "timeline_error", "message": "Erro interno ao processar a requisicao."}
        ) from exc


@router.get("/relatorios/calibracao", status_code=status.HTTP_200_OK)
def relatorio_calibracao(
    dias: int = 30,
    _: None = Depends(_check_api_rate_limit),
    unidades: set[int] | None = Depends(escopo_de_unidades),
) -> dict:
    """A confiança que o sensor reporta prediz falso alarme?

    `grade.confianca` era gravada em toda amostra e nunca lida — nem para
    decidir, nem para relatar. E o botão "falso alarme" já existia no
    fechamento, então o dado do outro lado também já vinha sendo coletado. O que
    faltava era alguém somar os dois.

    Sem isto, "qual a taxa de falso-positivo da instalação?" só tinha uma
    resposta honesta: não sei. Com isto, tem número — e, mais útil, tem número
    POR FAIXA de confiança, que é o que diz se o `CONF_LIMIAR` está no lugar
    certo.

    Ver `interface/repositories/calibracao.py` para o que liga um alerta às
    amostras que o geraram, e para o limite honesto do que isto mede.
    """
    from interface.repositories.calibracao import calibracao

    try:
        return calibracao(DB_PATH, dias=dias, unidades=unidades)
    except Exception as exc:
        logger.exception("calibracao_error", erro=str(exc))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "calibracao_error", "message": "Erro interno ao processar a requisicao."},
        ) from exc
