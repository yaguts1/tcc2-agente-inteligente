"""Tarefas de background iniciadas/paradas junto com o lifespan da app FastAPI.

Deployment de instancia unica (ver docs de deploy) — estas tasks nao usam
lock distribuido; rodar 2+ replicas duplicaria o processamento de eventos
de device e os backups.
"""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta, timezone

import structlog
from fastapi import FastAPI

from interface.api import reconcile_device_events
from servicos.backup import intervalo_de_backup_horas, scheduled_backup_task

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


def start_watchdog_task(app: FastAPI, db_path: str) -> asyncio.Task:
    """Vigia a AUSENCIA de dados.

    O motor de alertas so processa quando dado chega. Se o sensor morrer, o
    WiFi cair ou a ingestao quebrar, nao ha processamento, nao ha alerta — e a
    tela mostra "todos os pacientes em dia". O sistema falha CALADO, e silencio
    fica indistinguivel de normalidade.

    Este loop existe para que a falta de dado gere sinal por conta propria, sem
    depender de alguem abrir a tela: registra no log estruturado (para
    alertagem de infraestrutura) e atualiza a metrica Prometheus
    `pacientes_sem_monitoramento`, que pode disparar aviso operacional.
    """
    try:
        intervalo = max(10, int(os.getenv("MONITORAMENTO_CHECK_INTERVAL", "60")))
    except Exception:
        intervalo = 60

    async def _loop() -> None:
        from interface.repositories.monitoramento import resumo
        from servicos import metricas

        logger.info("watchdog_started", interval=intervalo)
        ultimo_alarme: set[str] = set()
        while True:
            try:
                dados = await asyncio.to_thread(resumo, db_path)
                metricas.registrar_pacientes_sem_monitoramento(dados["sem_monitoramento"])

                atuais = {p["paciente_id"] for p in dados["pacientes_sem_monitoramento"]}
                # Loga a transicao, nao o estado: repetir o alarme a cada ciclo
                # treinaria a equipe a ignorar a mensagem.
                novos = atuais - ultimo_alarme
                recuperados = ultimo_alarme - atuais
                if novos:
                    logger.error(
                        "monitoramento_interrompido",
                        pacientes=sorted(novos),
                        limite_min=dados["limite_min"],
                        motivo="sem leituras dentro do limite — sensor, rede ou ingestao",
                    )
                if recuperados:
                    logger.info("monitoramento_restabelecido", pacientes=sorted(recuperados))
                ultimo_alarme = atuais
            except asyncio.CancelledError:
                logger.info("watchdog_cancelled")
                raise
            except Exception as exc:
                logger.exception("watchdog_error", motivo=str(exc))
            try:
                await asyncio.sleep(intervalo)
            except asyncio.CancelledError:
                logger.info("watchdog_sleep_cancelled")
                raise

    task = asyncio.create_task(_loop(), name="watchdog_monitoramento")
    app.state._watchdog_task = task
    return task


async def stop_watchdog_task(app: FastAPI) -> None:
    task = getattr(app.state, "_watchdog_task", None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("watchdog_stopped")


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
    interval_hours = intervalo_de_backup_horas()

    async def _loop() -> None:
        logger.info("backup_scheduler_started", interval_hours=interval_hours, backup_dir=backup_dir)
        # Backup logo na subida, ANTES do primeiro sono. O loop dormia o
        # intervalo inteiro primeiro, entao uma instalacao reiniciada com mais
        # frequencia que o intervalo (24h por padrao) nunca chegava a fazer
        # backup nenhum — e foi exatamente o que se observou: o diretorio
        # estava vazio com o agendador "ativo" desde sempre.
        #
        # BACKUP_ON_START=0 desliga so o ciclo inicial (o periodico segue): serve
        # para processos de vida curta que instanciam a app sem serem a
        # instalacao de verdade — a suite de testes e o caso obvio, que sem isso
        # gravava dezenas de copias do banco de teste no diretorio real.
        primeira = os.getenv("BACKUP_ON_START", "1").strip().lower() not in ("0", "false", "no")
        while True:
            if not primeira:
                try:
                    await asyncio.sleep(interval_hours * 3600)
                except asyncio.CancelledError:
                    logger.info("backup_scheduler_sleep_cancelled")
                    raise
            primeira = False
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


def retencao_auditoria_dias() -> int | None:
    """Por quantos dias a trilha de auditoria e mantida. `None` = para sempre.

    Sem valor configurado NADA e expurgado, e isso e deliberado. O expurgo
    apaga trilha de auditoria: escolher um prazo "razoavel" por conta propria
    significaria destruir registro de acesso a dado clinico por causa de um
    default que ninguem decidiu. A LGPD pede que o dado nao seja mantido alem
    do necessario (Art. 15/16), mas o prazo adequado e politica da instituicao
    — e a instituicao a declara em AUDITORIA_RETENCAO_DIAS.

    Valor invalido tambem vira `None`: diante de uma configuracao que nao se
    entende, nao apagar e o lado seguro do erro.
    """
    bruto = os.getenv("AUDITORIA_RETENCAO_DIAS", "").strip()
    if not bruto:
        return None
    try:
        dias = int(bruto)
    except ValueError:
        logger.warning(
            "auditoria_retencao_invalida",
            valor=bruto,
            efeito="nenhum expurgo sera feito",
        )
        return None
    if dias <= 0:
        logger.warning(
            "auditoria_retencao_invalida",
            valor=bruto,
            motivo="precisa ser maior que zero",
            efeito="nenhum expurgo sera feito",
        )
        return None
    return dias


async def ciclo_housekeeping(db_path: str) -> dict[str, int]:
    """Um ciclo de limpeza. Devolve o que foi removido, para log e para teste.

    Esta no nivel do modulo (e nao aninhada no loop) para poder ser exercitada
    sem subir a app e sem esperar o intervalo.
    """
    from interface.repositories.auditoria import expurgar_anteriores_a
    from interface.repositories.sessoes import limpar_tokens_expirados
    from interface.tempo import agora_utc_naive

    resultado = {"tokens": 0, "auditoria": 0}

    try:
        resultado["tokens"] = await asyncio.to_thread(limpar_tokens_expirados, db_path)
        if resultado["tokens"]:
            logger.info("tokens_expirados_removidos", quantidade=resultado["tokens"])
    except Exception as exc:
        logger.exception("limpeza_tokens_falhou", motivo=str(exc))

    dias = retencao_auditoria_dias()
    if dias is None:
        return resultado

    try:
        corte = agora_utc_naive() - timedelta(days=dias)
        corte_ms = int(corte.replace(tzinfo=timezone.utc).timestamp() * 1000)
        resultado["auditoria"] = await asyncio.to_thread(
            expurgar_anteriores_a, db_path, corte_ms
        )
        if resultado["auditoria"]:
            # `warning`, nao `info`: apagar trilha de auditoria e um evento que
            # alguem precisa ver passar no log, ainda que esperado.
            logger.warning(
                "auditoria_expurgada",
                quantidade=resultado["auditoria"],
                retencao_dias=dias,
                corte=corte.strftime("%Y-%m-%dT%H:%M:%S"),
            )
    except Exception as exc:
        logger.exception("expurgo_auditoria_falhou", motivo=str(exc))

    return resultado


def start_housekeeping_task(app: FastAPI, db_path: str) -> asyncio.Task:
    """Limpezas periodicas de tabelas que so crescem.

    Duas rotinas existiam prontas e sem nenhum chamador em producao — so os
    testes as exercitavam:

    * `limpar_tokens_expirados`: revogacoes de token que ja passaram da
      validade. Depois de expirado o token seria recusado de qualquer forma,
      entao a linha nao serve para nada e a tabela crescia indefinidamente.
      Roda sempre; nao ha dado a perder.

    * `expurgar_anteriores_a` (trilha de auditoria): so roda quando
      AUDITORIA_RETENCAO_DIAS estiver definido. Ver `retencao_auditoria_dias`.
      O proprio expurgo se registra na trilha, entao a remocao fica
      documentada dentro do que ela modificou.
    """
    try:
        intervalo_horas = max(1, int(os.getenv("HOUSEKEEPING_INTERVAL_HOURS", "24")))
    except ValueError:
        intervalo_horas = 24

    async def _loop() -> None:
        logger.info(
            "housekeeping_started",
            interval_hours=intervalo_horas,
            retencao_auditoria_dias=retencao_auditoria_dias(),
        )
        # Dorme ANTES do primeiro ciclo — o contrario do agendador de backup,
        # e de proposito. La, "dormir primeiro" era o defeito: uma instalacao
        # reiniciada com mais frequencia que o intervalo nunca fazia backup, e
        # ficar sem backup e o lado perigoso do erro. Aqui e o inverso: o ciclo
        # APAGA (tokens e, se configurado, trilha de auditoria). Nao rodar
        # apenas adia uma limpeza; rodar a cada restart faria o expurgo
        # disparar toda subida da app. Falha para o lado que preserva dado.
        while True:
            try:
                await asyncio.sleep(intervalo_horas * 3600)
            except asyncio.CancelledError:
                logger.info("housekeeping_sleep_cancelled")
                raise
            try:
                await ciclo_housekeeping(db_path)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("housekeeping_error", motivo=str(exc))

    task = asyncio.create_task(_loop(), name="housekeeping")
    app.state._housekeeping_task = task
    return task


async def stop_housekeeping_task(app: FastAPI) -> None:
    task = getattr(app.state, "_housekeeping_task", None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("housekeeping_stopped")
