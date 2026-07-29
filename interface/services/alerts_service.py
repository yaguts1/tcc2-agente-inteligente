"""Logica de negocio de alertas: listagem no formato do frontend,
reconhecimento/conclusao (individual e em lote) e exportacao. Extraido de
interface/routers/alerts.py para manter o router focado em parsing de
request/response HTTP (mesmo padrao ja aplicado em routers/ingestao.py).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import List, Literal, NamedTuple

import structlog

from interface.api_shared import DB_PATH, api_cache
from interface.dao import (
    alterar_status_alerta,
    inserir_timeline_event,
    listar_fichas_pacientes,
    selecionar_alertas_janela,
)
from interface.alert_id import montar_alert_id, partir_alert_id
from interface.repositories.alertas import (
    MOTIVO_REPOSICIONADO,
    MOTIVOS_SEM_REPOSICIONAMENTO,
    ORIGEM_EQUIPE,
)
from interface.repositories.timeline import ultimo_evento_por_paciente
from interface.services.paciente_service import dividir_cama
from interface.tempo import agora_utc_naive, para_iso_utc
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


class PaginaDeAlertas(NamedTuple):
    """Uma página de alertas e QUANTOS existem no total com aqueles filtros.

    O `total` existe porque a lista sozinha mente por omissão: 100 alertas
    devolvidos com `limit=100` são indistinguíveis de "há exatamente 100". O
    dashboard filtra em memória sobre o que recebeu, então um corte invisível
    esconde paciente atrasado sem nada na tela indicar que houve corte.
    """

    itens: list[dict]
    total: int


async def listar_alertas_frontend(
    horas: int | None = 24,
    risk_level: str | None = None,
    status_filter: str | None = None,
    room: str | None = None,
    limit: int = 100,
    offset: int = 0,
    unidades: set[int] | None = None,
) -> list[dict]:
    """Apenas os itens da página. Ver `listar_alertas_frontend_paginado`."""
    pagina = await listar_alertas_frontend_paginado(
        horas, risk_level, status_filter, room, limit, offset, unidades
    )
    return pagina.itens


async def listar_alertas_frontend_paginado(
    horas: int | None = 24,
    risk_level: str | None = None,
    status_filter: str | None = None,
    room: str | None = None,
    limit: int = 100,
    offset: int = 0,
    unidades: set[int] | None = None,
) -> PaginaDeAlertas:
    """Busca alertas no formato consumido pelo frontend React, com o total
    correspondente aos filtros e cache de 30s por combinação."""
    # A UNIDADE ENTRA NA CHAVE DO CACHE.
    #
    # Sem isso o escopo vira um vazamento com 30 segundos de duracao: a
    # enfermeira da ala A carrega a lista, a chave nao distingue quem perguntou,
    # e a proxima requisicao — de outra ala, ou de um usuario sem unidade
    # nenhuma — recebe a pagina dela pronta do cache. Seria pior que nao ter
    # escopo, porque a tela pareceria correta.
    escopo = "todas" if unidades is None else ",".join(str(u) for u in sorted(unidades))
    cache_key = (
        f"alerts:{horas}:{risk_level}:{status_filter}:{room}:{limit}:{offset}:u={escopo}"
    )
    cached_result = await api_cache.get(cache_key)
    if cached_result is not None:
        return PaginaDeAlertas(itens=cached_result["itens"], total=cached_result["total"])

    # Estrutura em 3 queries de custo fixo, independentemente do numero de
    # alertas. Antes eram duas consultas POR ALERTA (obter_ficha_paciente e
    # selecionar_timeline), cada uma abrindo a propria conexao: 500 alertas na
    # janela viravam ~1000 conexoes. Pior, os filtros e o limit/offset so eram
    # aplicados DEPOIS desse laco, entao limit=10 pagava o custo inteiro.
    raw_alerts = selecionar_alertas_janela(DB_PATH, horas)

    # 1) Filtros que nao dependem do banco, aplicados ANTES de qualquer I/O.
    candidatos = []
    for a in raw_alerts:
        risk_level_val = _RISK_MAP.get(str(a.get("perfil") or "medio"), "medium")
        status_val = _STATUS_MAP.get(str(a.get("status") or "aberto"), "pending")
        if risk_level and risk_level_val != risk_level:
            continue
        if status_filter and status_val != status_filter:
            continue
        candidatos.append((a, risk_level_val, status_val))

    # 2) Fichas de todos os pacientes VISIVEIS de uma vez (1 query).
    #
    # Esta consulta e o porteiro do escopo por unidade. Como todo alerta ja
    # precisa da ficha para resolver nome e leito, restringir as fichas
    # restringe os alertas pelo mesmo caminho — sem uma segunda regra de
    # visibilidade que pudesse divergir da primeira.
    fichas = {
        str(f.get("paciente_id")): f
        for f in listar_fichas_pacientes(DB_PATH, incluir_rotinas=False, unidades=unidades)
    }

    if unidades is not None:
        # Alerta de paciente fora do escopo sai da lista. Sem isto o alerta
        # apareceria com o ID cru no lugar do nome e o leito vazio — vazando a
        # existencia (e o risco) de um paciente de outra ala pela porta de tras.
        #
        # So no ramo escopado: para admin (`unidades is None`) um alerta sem
        # ficha continua listado como sempre foi, porque ali o sintoma e dado
        # orfao, nao vazamento.
        candidatos = [c for c in candidatos if str(c[0].get("paciente_id")) in fichas]

    def _quarto_e_leito(paciente_id: str) -> tuple[str, str, str]:
        ficha = fichas.get(str(paciente_id))
        # `or paciente_id` fecha o caso de ficha existente com `nome` NULL, que
        # o banco permite. Sem ele o contrato prometeria `patientName: str` e
        # entregaria `null` — e a tela quebraria num `.toLowerCase()` da busca.
        nome = (ficha.get("nome") if ficha else None) or paciente_id
        # Mesma funcao que a tela de Pacientes usa. Aqui a separacao era por
        # BARRA enquanto o cadastro junta com HIFEN, entao nunca casava: o
        # dashboard mostrava o `cama_id` inteiro como quarto e o leito vazio.
        quarto, leito = dividir_cama(ficha.get("cama_id") if ficha else None)
        return nome, quarto, leito

    # O filtro por quarto depende da ficha, entao vem depois do passo 2.
    if room:
        alvo = room.lower()
        candidatos = [
            c for c in candidatos
            if alvo in _quarto_e_leito(c[0].get("paciente_id"))[1].lower()
        ]

    # Quantos alertas casam com os filtros, independentemente da pagina. E o
    # numero que torna o corte VISIVEL: sem ele, uma lista de 100 alertas e
    # indistinguivel de "existem exatamente 100" — e o dashboard filtra em
    # memoria sobre o que recebeu, entao um corte silencioso esconde paciente
    # atrasado do enfermeiro sem nenhum sinal na tela.
    total = len(candidatos)

    # 3) Pagina ANTES de buscar a timeline: so o que vai ser devolvido custa I/O.
    pagina = candidatos[offset: offset + limit]

    ultimos = ultimo_evento_por_paciente(
        DB_PATH,
        paciente_ids=list({str(a.get("paciente_id")) for a, _, _ in pagina}),
        tipos=["alert_ack", "repositioned", "alert_close", "alert_open"],
    )

    results: list[dict] = []
    for a, risk_level_val, status_val in pagina:
        paciente_id = a.get("paciente_id")
        inicio = a.get("inicio")
        janela_min = int(a.get("janela_min") or 0)
        patient_name, room_val, bed = _quarto_e_leito(paciente_id)

        # Quando o proximo reposicionamento vence.
        #
        # `alerta.inicio` NAO e o inicio da imobilidade: o motor grava nele o
        # instante em que a janela ESTOUROU (ver nucleo/decisor.py:
        # `detection_time = run_inicio + janela`). Ou seja, quando existe um
        # alerta aberto o paciente JA esta atrasado desde `inicio`.
        #
        # Somar a janela de novo — como era feito aqui — jogava o vencimento
        # para o futuro e a tela exibia um alerta ABERTO dizendo que o
        # reposicionamento so venceria dali a uma janela inteira. Para o perfil
        # alto isso e uma hora de falsa tranquilidade.
        #
        # Semantica correta por estado:
        #   pendente/reconhecido -> vence em `inicio` (ja vencido);
        #   concluido            -> paciente virado em `fim`, proximo em
        #                           `fim + janela`.
        fim = a.get("fim")
        if status_val == "completed" and fim:
            try:
                base = datetime.fromisoformat(str(fim)[:19]) + timedelta(minutes=janela_min)
                next_iso = base.strftime("%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError):
                next_iso = fim
        else:
            next_iso = inicio

        results.append(
            {
                "id": montar_alert_id(paciente_id, inicio),
                # O paciente, explicito. A tela precisava dele para filtrar e o
                # obtinha desmontando o `id` com `split('__')[0]` — reimplementando
                # o formato do identificador do lado do cliente, onde ele passa a
                # quebrar em silencio no dia em que o formato mudar.
                "patientId": paciente_id,
                "patientName": patient_name,
                "room": room_val,
                "bed": bed,
                # ISO com offset explicito: sem ele o browser interpreta a
                # string como hora LOCAL e exibe tudo 3h adiantado no Brasil.
                "lastRepositioning": para_iso_utc(ultimos.get(str(paciente_id)) or inicio),
                "nextRepositioning": para_iso_utc(next_iso),
                "riskLevel": risk_level_val,
                "status": status_val,
                # Quem fechou: 'equipe' | 'sensor' | 'sistema' | null.
                # A tela precisa disto para recalcular as estatisticas quando ha
                # filtro ativo — sem o campo, a visao filtrada voltaria a somar
                # adesao da equipe com movimento espontaneo, que e exatamente o
                # que `completedByTeam` existe para separar.
                "closureOrigin": a.get("origem_fechamento"),
                "closedBy": a.get("fechado_por"),
            }
        )

    await api_cache.set(cache_key, {"itens": results, "total": total}, ttl_seconds=30)
    return PaginaDeAlertas(itens=results, total=total)


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
        _, inicio = partir_alert_id(alert_id)
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
        # Sem isto o WebSocketFilter nao tem contra o que decidir e, por
        # seguranca, nao entrega nada a conexao escopada — o alerta simplesmente
        # nao chegaria na tela da propria ala.
        "unidade_id": _unidade_do_paciente(paciente_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _unidade_do_paciente(paciente_id: str) -> int | None:
    """Unidade atual do paciente, para o filtro do WebSocket."""
    from interface.dao import obter_ficha_paciente

    try:
        ficha = obter_ficha_paciente(DB_PATH, paciente_id, incluir_rotinas=False)
    except Exception:
        logger.warning("unidade_do_paciente_falhou", paciente_id=paciente_id, exc_info=True)
        return None
    return None if ficha is None else ficha.get("unidade_id")


def montar_payload_alerta_novo(paciente_id: str, alerta: dict) -> dict:
    """Mensagem de um alerta RECEM-CRIADO pelo motor.

    Mesmos campos do `alert_update` porque e contra eles que o WebSocketFilter
    filtra; muda o `type`, para o cliente distinguir "apareceu um alerta" de
    "o status de um alerta mudou" — sao reacoes diferentes na tela.
    """
    inicio = str(alerta.get("inicio") or "")
    return {
        "type": "alert_new",
        "alert_id": montar_alert_id(paciente_id, inicio),
        "status": _STATUS_MAP.get(str(alerta.get("status") or "aberto"), "pending"),
        "patient_id": paciente_id,
        "severity": _RISK_MAP.get(str(alerta.get("perfil") or "").lower()),
        "alert_type": alerta.get("tipo"),
        "unidade_id": _unidade_do_paciente(paciente_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


_LOOP: asyncio.AbstractEventLoop | None = None


def registrar_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Guarda o loop principal, chamado no startup (interface/web.py)."""
    global _LOOP
    _LOOP = loop


def agendar_anuncio(alertas: list[dict]) -> None:
    """Agenda o anuncio dos alertas novos a partir de QUALQUER contexto.

    A ingestao HTTP (`POST /api/eventos`) e um handler `def`, ou seja, roda no
    threadpool do FastAPI — fora do event loop. `asyncio.get_running_loop()`
    levanta RuntimeError ali, entao agendar so com `create_task` nao anunciaria
    nada no caminho principal, que e justamente o do sensor real.

    Por isso as duas portas: dentro do loop, `create_task`; de outra thread,
    `run_coroutine_threadsafe` no loop guardado no startup.
    """
    if not alertas:
        return
    copia = list(alertas)
    try:
        asyncio.get_running_loop().create_task(anunciar_alertas_novos(copia))
        return
    except RuntimeError:
        pass

    loop = _LOOP
    if loop is None or loop.is_closed():
        # Sem loop registrado nao ha cliente WS neste processo (scripts, testes
        # sincronos). Nao e erro, e ausencia de destinatario.
        return
    try:
        asyncio.run_coroutine_threadsafe(anunciar_alertas_novos(copia), loop)
    except Exception:
        logger.warning("agendar_anuncio_falhou", exc_info=True)


async def anunciar_alertas_novos(alertas: list[dict]) -> None:
    """Publica no WS os alertas que o motor acabou de abrir.

    NADA anunciava alerta novo: `broadcast` so era chamado por reconhecer e
    completar. Como o frontend desliga o polling enquanto o WS esta conectado,
    o resultado era o pior possivel para um monitor de leito — a tela ficava
    congelada na lista carregada na abertura da pagina e o alerta que manda
    virar o paciente nunca chegava. O docstring da rota /ws/alerts afirmava
    justamente o contrario ("New alerts will be pushed").

    Tambem invalida o cache de 30s da listagem: sem isso, o refetch disparado
    pela mensagem poderia devolver a lista velha, ainda sem o alerta.
    """
    if not alertas:
        return
    await api_cache.clear()
    for alerta in alertas:
        paciente_id = str(alerta.get("paciente_id") or "")
        if not paciente_id:
            continue
        try:
            await ws_manager_optimized.broadcast(montar_payload_alerta_novo(paciente_id, alerta))
        except Exception:
            # Um cliente WS problematico nao pode impedir a ingestao da amostra
            # seguinte — mas o silencio aqui e o que escondeu o defeito original.
            logger.warning("broadcast_alerta_novo_falhou", paciente_id=paciente_id, exc_info=True)


def _motivo_efetivo(definir_fim: bool, motivo: str | None) -> str | None:
    """Motivo que sera gravado.

    Ausente vale como `reposicionado`, o caso comum: exigir escolha explicita
    em toda conclusao adicionaria atrito na acao mais frequente da ala, e atrito
    na acao frequente e o que faz a equipe procurar o atalho. Quem faz o comum
    nao escolhe nada; a excecao e que precisa ser dita.

    `acknowledge` nao grava motivo nenhum: reconhecer e dizer "eu vi", nao
    resolver.
    """
    if not definir_fim:
        return None
    return motivo or MOTIVO_REPOSICIONADO


def _avisar_motor_do_reposicionamento(paciente_id: str) -> None:
    """Fecha o ciclo entre o clique da enfermagem e o estado do motor.

    Sem isto, concluir um alerta na tela deixava `alerta_atual` preenchido no
    decisor e o paciente ficava PERMANENTEMENTE sem alerta novo — com o
    dashboard verde. Ver `ProcessadorIncremental.marcar_reposicionado`.

    Import tardio: `ingestao_service` (dono do PROCESSADOR) importa daqui para
    anunciar alertas novos, entao o import no topo fecharia ciclo.

    Falha aqui nao derruba a operacao — o alerta ja foi fechado no banco e o
    clique da enfermeira nao pode virar erro 500 por causa do motor — mas
    tambem nao passa em silencio: um motor desatualizado e exatamente o defeito
    que esta funcao existe para corrigir.
    """
    try:
        from interface.services.ingestao_service import PROCESSADOR

        PROCESSADOR.marcar_reposicionado(paciente_id)
    except Exception:
        logger.warning("motor_nao_soube_do_reposicionamento", paciente_id=paciente_id, exc_info=True)


async def _aplicar_operacao(
    alert_id: str,
    user: str,
    operacao: Literal["acknowledge", "complete"],
    motivo: str | None = None,
) -> None:
    """Aplica reconhecer/completar a um único alerta: atualiza status,
    registra timeline, faz broadcast via WS e invalida o cache."""
    config = _OPERACOES[operacao]
    paciente_id, inicio = partir_alert_id(alert_id)
    motivo = _motivo_efetivo(config["definir_fim"], motivo)

    alterar_status_alerta(
        DB_PATH,
        paciente_id,
        inicio,
        config["novo_status"],
        config["definir_fim"],
        fechado_por=user if config["definir_fim"] else None,
        origem_fechamento=ORIGEM_EQUIPE,
        usuario=user,
        motivo=motivo,
    )

    if config["definir_fim"]:
        # So reinicia o motor quando o paciente foi DE FATO reposicionado.
        #
        # "Recusa do paciente", "em procedimento", "contraindicado" e "falso
        # alarme" fecham a linha na tela, mas NAO houve alivio de pressao —
        # zerar a corrida ali daria ao paciente credito por um movimento que
        # nao aconteceu, e adiaria o proximo alerta de uma janela inteira
        # justamente em quem continua imovel.
        if motivo is None or motivo not in MOTIVOS_SEM_REPOSICIONAMENTO:
            _avisar_motor_do_reposicionamento(paciente_id)
        else:
            logger.info(
                "motor_nao_reiniciado_por_motivo",
                paciente_id=paciente_id,
                motivo=motivo,
            )

    try:
        # Idem: UTC naive, o formato do resto do banco.
        agora = agora_utc_naive().replace(microsecond=0)
        ts_iso = agora.strftime("%Y-%m-%dT%H:%M:%S")
        ts_ms = int(agora.replace(tzinfo=timezone.utc).timestamp() * 1000)
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


async def completar_alerta(alert_id: str, user: str, motivo: str | None = None) -> None:
    await _aplicar_operacao(alert_id, user, "complete", motivo=motivo)


async def processar_lote(
    alert_ids: List[str],
    user: str,
    operacao: Literal["acknowledge", "complete"],
    motivo: str | None = None,
) -> dict:
    """Aplica reconhecer/completar a vários alertas em paralelo (thread pool
    para as operações de banco), com broadcast em background e métricas."""
    config = _OPERACOES[operacao]
    motivo = _motivo_efetivo(config["definir_fim"], motivo)
    processed = 0
    failed = 0
    errors: List[dict] = []
    broadcast_tasks: List = []

    async def _process_alert(alert_id: str) -> tuple[bool, dict | None]:
        try:
            paciente_id, inicio = partir_alert_id(alert_id)
            await asyncio.to_thread(
                partial(
                    alterar_status_alerta,
                    DB_PATH,
                    paciente_id,
                    inicio,
                    config["novo_status"],
                    config["definir_fim"],
                    fechado_por=user if config["definir_fim"] else None,
                    origem_fechamento=ORIGEM_EQUIPE,
                    usuario=user,
                    motivo=motivo,
                )
            )
            if config["definir_fim"] and (
                motivo is None or motivo not in MOTIVOS_SEM_REPOSICIONAMENTO
            ):
                # O lote precisa do MESMO aviso ao motor que a operacao unitaria:
                # e por aqui que passa a maior parte dos fechamentos (o botao de
                # selecionar tudo da tela), entao esquecer aqui deixaria o defeito
                # vivo justamente no caminho mais usado.
                await asyncio.to_thread(_avisar_motor_do_reposicionamento, paciente_id)
            try:
                # UTC naive no formato do resto do banco. Estes dois pontos
                # gravavam `2026-07-25T03:42:24.229283+00:00` enquanto todos os
                # outros eventos usam `2026-07-25T03:42:24`, deixando a coluna
                # `ts` com dois formatos. Nao quebra nada hoje (a ordenacao usa
                # `ts_ms` e o endpoint normaliza com `para_iso_utc`), mas e uma
                # armadilha para o proximo consumidor de `ts`.
                agora = agora_utc_naive().replace(microsecond=0)
                ts_iso = agora.strftime("%Y-%m-%dT%H:%M:%S")
                ts_ms = int(agora.replace(tzinfo=timezone.utc).timestamp() * 1000)
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
