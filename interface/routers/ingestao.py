from __future__ import annotations

import asyncio
import json
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status, WebSocket, WebSocketDisconnect

from interface.api_shared import (
    DB_PATH,
    _aplicar_rate_limit,
    _check_api_rate_limit,
    iterar_linhas_jsonl,
    tipo_de_conteudo_aceito,
)
from interface.dependencies import (
    TOKEN_DISPOSITIVO_HEADER,
    get_current_user,
    token_dispositivo_configurado,
    verificar_token_dispositivo,
)
from interface.repositories.devices import inserir_device_event, registrar_device, resolver_paciente_por_device_em
from interface.schemas import ApiResponse
from interface.services.ingestao_service import (
    _do_reconcile_bed,
    _reconcile_lock,
    normalizar_payload,
    processar_eventos_filtrados,
    reconcile_device_events,
    registrar_evento,
)
from quality.filtro import filtrar as filtrar_evento, flush_filtro
from servicos import metricas

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["ingestao"])


def _ts_da_medicao(payload: Dict[str, Any], device_id: str | None) -> datetime:
    """Quando a amostra foi MEDIDA, em UTC naive (a convencao do banco).

    Existe porque o instante da medicao e o da chegada podem estar horas
    afastados — o firmware repete indefinidamente enquanto a falha for
    temporaria — e e o da MEDICAO que decide de quem e a leitura na
    reconciliacao.
    """
    bruto = payload.get("ts_utc")
    if bruto:
        try:
            dt = datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except (ValueError, TypeError):
            logger.warning("ws_ts_utc_ilegivel", device_id=device_id, ts_utc=str(bruto))
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post(
    "/eventos",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
)
def receber_evento(
    request: Request,
    payload: Dict[str, Any],
    _: None = Depends(_aplicar_rate_limit),
    __: None = Depends(verificar_token_dispositivo),
) -> ApiResponse:
    device_header = request.headers.get("X-Device-Id")
    evento = normalizar_payload(payload, device_header)
    evento_dict = evento.model_dump(mode="python")

    # Ensure device known. Falha aqui é benigna: o device já pode estar
    # registrado e a amostra ainda pode ser processada — mas precisa ser vista.
    try:
        registrar_device(DB_PATH, evento.device_id, meta=None)
    except Exception:
        logger.warning("registrar_device_falhou", device_id=evento.device_id, exc_info=True)

    # Resolve paciente by device and timestamp if paciente_id not provided
    try:
        ts_ms = int(evento.ts_utc.timestamp() * 1000)
    except Exception:
        ts_ms = None
    if not evento.paciente_id and ts_ms is not None:
        # Falha na resolução é benigna: cai no caminho de evento órfão abaixo,
        # que persiste a amostra para reconciliação posterior.
        try:
            pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
            if pid:
                evento.paciente_id = pid
                evento_dict["paciente_id"] = pid
        except Exception:
            logger.warning(
                "resolver_paciente_falhou", device_id=evento.device_id, ts_ms=ts_ms, exc_info=True
            )

    metricas.registrar_recebido()

    # If still no paciente_id, persist raw device event for later reconciliation and return
    if not evento.paciente_id:
        # Este é o ÚNICO lugar onde a amostra é guardada. Se falhar, o dado do
        # sensor está perdido — não pode responder "accepted".
        try:
            ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
            ts_ms = int(evento.ts_utc.timestamp() * 1000)
            ev_id = inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
        except Exception as exc:
            logger.exception("evento_orfao_nao_persistido", device_id=evento.device_id)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "persistencia_indisponivel",
                    "message": "Falha ao armazenar o evento; reenvie.",
                },
            ) from exc
        logger.info("evento_sem_paciente", device_id=evento.device_id, event_id=ev_id)
        return ApiResponse(
            code="accepted",
            message="Evento recebido mas sem paciente atribuido; armazenado para reconciliação.",
            ids={
                "device_id": evento.device_id,
                "processados": 0,
                "alertas": 0,
                "event_id": ev_id,
            },
        )

    resultado = filtrar_evento(evento_dict)

    if resultado.descartado:
        metricas.registrar_descartado()
        logger.info(
            "evento_descartado",
            device_id=evento.device_id,
            paciente_id=evento.paciente_id,
            motivo=resultado.motivo,
        )
        return ApiResponse(
            code="accepted",
            message="Evento descartado pelo filtro.",
            ids={
                "device_id": evento.device_id,
                "processados": 0,
                "alertas": 0,
            },
        )

    if not resultado.prontos:
        logger.debug(
            "evento_bufferizado",
            device_id=evento.device_id,
            paciente_id=evento.paciente_id,
        )
        return ApiResponse(
            code="accepted",
            message="Evento armazenado aguardando ordenacao.",
            ids={
                "device_id": evento.device_id,
                "processados": 0,
                "alertas": 0,
            },
        )

    contagem: Dict[str, int] = defaultdict(int)
    total_alertas = processar_eventos_filtrados(resultado.prontos, contagem)
    processados = sum(contagem.values())

    logger.info(
        "eventos_processados",
        device_id=evento.device_id,
        pacientes=dict(contagem),
        alertas=total_alertas,
    )

    return ApiResponse(
        code="success",
        message="Eventos processados com sucesso.",
        ids={
            "pacientes": dict(contagem),
            "device_id": evento.device_id,
            "processados": processados,
            "alertas": total_alertas,
        },
    )


@router.post(
    "/grade",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
)
async def receber_grade(
    request: Request,
    arquivo: UploadFile = File(...),
    _: None = Depends(_aplicar_rate_limit),
    __: None = Depends(verificar_token_dispositivo),
) -> ApiResponse:
    if not tipo_de_conteudo_aceito(arquivo.content_type):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_content_type", "message": "Envie arquivo JSONL valido."},
        )

    device_header = request.headers.get("X-Device-Id")
    contagem_por_paciente: Dict[str, int] = defaultdict(int)
    dispositivos_vistos: set[str] = set()
    total_alertas = 0
    linhas_lidas = 0
    perdidos = 0  # amostras que nao puderam ser persistidas (reenviar resolve)
    rejeitadas: list[int] = []  # linhas malformadas (reenviar NAO resolve)

    try:
        async for linha in iterar_linhas_jsonl(arquivo):
            linhas_lidas += 1
            # Uma linha ruim nao aborta o lote.
            #
            # Antes, tanto o JSON invalido (400) quanto a estrutura invalida
            # (422, de dentro de `normalizar_payload`) interrompiam o upload no
            # meio. As linhas anteriores JA estavam gravadas — cada insercao
            # abre a propria conexao e comita — mas a resposta era so um erro,
            # sem numero algum: o cliente nao tinha como saber que metade do
            # arquivo entrou. Reenviar o arquivo era a unica saida, e o que
            # protegia contra a duplicacao era o cache de dedup em memoria, de
            # 2048 entradas por dispositivo, que um restart zera.
            #
            # Agora a linha ruim e contada e reportada, e o resto do lote segue.
            try:
                dados = json.loads(linha)
            except json.JSONDecodeError:
                rejeitadas.append(linhas_lidas)
                logger.warning(
                    "grade_linha_json_invalida", device_id=device_header, linha=linhas_lidas
                )
                continue
            try:
                evento = normalizar_payload(dados, device_header)
            except HTTPException:
                rejeitadas.append(linhas_lidas)
                logger.warning(
                    "grade_linha_estrutura_invalida",
                    device_id=device_header,
                    linha=linhas_lidas,
                )
                continue
            evento_dict = evento.model_dump(mode="python")
            dispositivos_vistos.add(evento.device_id)
            # ensure device registered (falha benigna: device já pode existir)
            try:
                registrar_device(DB_PATH, evento.device_id, meta=None)
            except Exception:
                logger.warning("registrar_device_falhou", device_id=evento.device_id, exc_info=True)
            # try resolve paciente
            try:
                ts_ms = int(evento.ts_utc.timestamp() * 1000)
            except Exception:
                ts_ms = None
            if not evento.paciente_id and ts_ms is not None:
                # Falha benigna: cai no caminho de órfão, que persiste a amostra.
                try:
                    pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
                    if pid:
                        evento.paciente_id = pid
                        evento_dict["paciente_id"] = pid
                except Exception:
                    logger.warning(
                        "resolver_paciente_falhou", device_id=evento.device_id, ts_ms=ts_ms, exc_info=True
                    )
            metricas.registrar_recebido()
            # if still no paciente, store raw device event and continue
            if not evento.paciente_id:
                # Perder isto significa perder a amostra. Não aborta o lote
                # inteiro por uma linha, mas contabiliza e reporta na resposta.
                try:
                    ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
                    if ts_ms is None:
                        ts_ms = int(evento.ts_utc.timestamp() * 1000)
                    inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
                except Exception:
                    perdidos += 1
                    logger.exception(
                        "evento_orfao_nao_persistido",
                        device_id=evento.device_id,
                        linha=linhas_lidas,
                    )
                continue
            resultado = filtrar_evento(evento_dict)
            if resultado.descartado:
                metricas.registrar_descartado()
                continue
            if resultado.prontos:
                total_alertas += processar_eventos_filtrados(resultado.prontos, contagem_por_paciente)
    finally:
        await arquivo.close()

    # Flush restrito aos dispositivos deste upload.
    #
    # `flush_filtro()` sem argumento esvazia o buffer de reordenacao de TODOS os
    # dispositivos, inclusive os que estao transmitindo ao vivo por outra
    # conexao. Aquelas amostras eram processadas antes da janela de jitter
    # fechar, e o buffer que existia justamente para reorden-las desaparecia:
    # a amostra seguinte, com `ts` anterior, chegava depois e ja nao tinha com o
    # que ser reordenada.
    for dispositivo in dispositivos_vistos:
        flush_eventos = flush_filtro(dispositivo)
        if flush_eventos:
            total_alertas += processar_eventos_filtrados(flush_eventos, contagem_por_paciente)
    processados = sum(contagem_por_paciente.values())

    # Nenhuma linha aproveitavel: 400, e so aqui.
    #
    # A regra que separa este caso do anterior e o que ficou gravado. Se alguma
    # linha entrou, abortar com erro apagaria o unico registro de que ela
    # entrou, e o cliente reenviaria o arquivo inteiro — por isso o lote misto
    # responde 200 com a contagem. Quando TODAS as linhas foram rejeitadas nao
    # ha nada gravado para preservar, e o arquivo esta errado: dizer "sucesso"
    # e que seria mentira.
    if linhas_lidas and len(rejeitadas) == linhas_lidas:
        logger.warning(
            "grade_arquivo_ilegivel", device_id=device_header, linhas=linhas_lidas
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_jsonl",
                "message": f"Nenhuma das {linhas_lidas} linhas do arquivo pode ser lida.",
                "linhas_rejeitadas": rejeitadas[:20],
            },
        )

    logger.info(
        "grade_processada",
        device_id=device_header,
        linhas=linhas_lidas,
        processados=processados,
        alertas=total_alertas,
        perdidos=perdidos,
        rejeitadas=len(rejeitadas),
    )

    # O que nao entrou sai junto do resultado. Um upload parcial nao pode ser
    # indistinguivel de um completo (o mesmo defeito que o relatorio truncado
    # tinha), e as duas falhas pedem acoes opostas: `perdidos` e transitorio e
    # se resolve reenviando; `rejeitadas` e malformacao e reenviar repete o erro.
    partes = [f"{linhas_lidas} linhas lidas", f"{processados} amostras processadas"]
    if perdidos:
        partes.append(f"{perdidos} nao armazenadas (reenvie)")
    if rejeitadas:
        partes.append(f"{len(rejeitadas)} linhas invalidas descartadas")
    mensagem = "; ".join(partes) + "."

    return ApiResponse(
        code="partial" if (perdidos or rejeitadas) else "success",
        message=mensagem,
        ids={
            "pacientes": dict(contagem_por_paciente),
            "device_id": device_header,
            "linhas": linhas_lidas,
            "processados": processados,
            "alertas": total_alertas,
            "perdidos": perdidos,
            "rejeitadas": len(rejeitadas),
            # Amostra dos numeros de linha para o operador achar o problema no
            # arquivo, limitada para nao inflar a resposta com um lote todo ruim.
            "linhas_rejeitadas": rejeitadas[:20],
        },
    )


# As duas rotas de reconciliacao ESCREVEM em prontuario (grade, eventos e os
# alertas calculados em cima deles), mas ficaram sem dependencia nenhuma
# enquanto todas as vizinhas exigiam sessao — inclusive `GET /api/device_events`
# (routers/devices.py:25), que so LE a mesma fila. Sao acionadas pela tela de
# administracao, entao a exigencia e a mesma do resto do painel.
@router.post(
    "/device_events/reconcile",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user), Depends(_check_api_rate_limit)],
)
async def api_reconcile_device_events(device_id: str | None = None, limit: int = 100) -> dict:
    """Attempt to reconcile stored raw device events into patient events."""
    # delegate to shared reconcile helper which uses a lock and runs in a thread
    result = await reconcile_device_events(device_id=device_id, limit=limit)
    return result


@router.post(
    "/device_events/reconcile_bed/{cama_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user), Depends(_check_api_rate_limit)],
)
async def api_reconcile_bed_events(cama_id: str, limit: int = 1000) -> dict:
    """Reconcilia os eventos orfaos de um leito, cada um para o dono do instante."""
    async with _reconcile_lock:
        return await asyncio.to_thread(_do_reconcile_bed, cama_id, limit)


@router.websocket("/ws/eventos")
async def websocket_eventos(websocket: WebSocket):
    """
    WebSocket endpoint for receiving events from devices (ESP32).
    Protocol:
    1. Client connects
    2. Client sends auth: {"device_id": "...", "cama_id": "...", "token": "..."}
    3. Server responds: {"status": "connected", "device_id": "..."
    4. Client sends events: {"seq": 1, ...}
    5. Server responds ACK: {"status": "ok", "seq": 1}

    O token pode vir no header X-Device-Token (handshake HTTP) ou no campo
    `token` da mensagem de auth — o segundo caminho existe porque nem toda
    biblioteca de WebSocket em firmware permite definir headers.
    """
    await websocket.accept()
    device_id = None

    try:
        # 1. Authentication handshake
        try:
            auth_data = await websocket.receive_json()
        except Exception:
            await websocket.send_json({"status": "error", "error": "Invalid JSON"})
            await websocket.close()
            return

        device_id = auth_data.get("device_id")
        if not device_id:
            await websocket.send_json({"status": "error", "error": "Missing device_id"})
            await websocket.close()
            return

        esperado = token_dispositivo_configurado()
        if esperado:
            recebido = websocket.headers.get(TOKEN_DISPOSITIVO_HEADER) or auth_data.get("token") or ""
            if not secrets.compare_digest(recebido, esperado):
                logger.warning("ws_device_token_invalido", device_id=device_id)
                await websocket.send_json({"status": "error", "error": "invalid_device_token"})
                await websocket.close()
                return

        # Register device if needed (falha benigna: device já pode existir)
        try:
            registrar_device(DB_PATH, device_id, meta={"cama_id": auth_data.get("cama_id")})
        except Exception:
            logger.warning("registrar_device_falhou", device_id=device_id, exc_info=True)

        await websocket.send_json({"status": "connected", "device_id": device_id})

        # 2. Event loop
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({"status": "error", "error": "Invalid JSON"})
                    continue

                # Process event
                # `pop`, e nao `get`: `seq` e metadado de CORRELACAO do
                # protocolo, nao parte da amostra. `EventPayload` tem
                # `extra="forbid"`, entao deixa-lo no dicionario reprovava a
                # validacao inteira.
                #
                # O efeito era um beco sem saida para o firmware, confirmado
                # contra o servidor rodando:
                #
                #   * sem `seq`, a amostra era processada corretamente mas o
                #     ACK nunca saia (o envio e guardado pelo `if seq is not
                #     None` la embaixo) — o dispositivo nao tinha como saber se
                #     a leitura chegou;
                #   * com `seq`, a validacao falhava com `extra_forbidden`, a
                #     amostra caia no caminho degradado de evento ORFAO e o
                #     servidor respondia "ok" — um ACK que dizia "entregue"
                #     quando o que houve foi "guardei cru para reconciliar
                #     depois".
                #
                # Nao havia combinacao em que o firmware recebesse ACK e a
                # amostra fosse processada. Era por isso que o firmware
                # WebSocket contava ACK no envio: nao havia ACK de verdade
                # para esperar.
                seq = payload.pop("seq", None)

                # Normalize and process
                try:
                    # Add device_id if missing
                    if not payload.get("device_id"):
                        payload["device_id"] = device_id

                    # Validate payload structure
                    # We use a permissive validation here since WS events might be slightly different
                    # or we want to be fast. But let's try to use the standard flow.

                    # Convert to EventPayload-like dict
                    if "ts_utc" not in payload:
                        # Carimbar a amostra com a hora de CHEGADA e uma
                        # aproximacao, nao um dado: o firmware agora repete
                        # indefinidamente enquanto a falha for temporaria, entao
                        # uma amostra pode chegar horas depois de medida. Sem
                        # `ts_utc` nao ha como saber quando ela ocorreu — o
                        # default fica, porque descartar seria pior, mas
                        # registrado, porque distorce a linha do tempo do
                        # paciente.
                        payload["ts_utc"] = datetime.now(timezone.utc).isoformat()
                        logger.warning(
                            "ws_evento_sem_ts_utc",
                            device_id=device_id,
                            motivo="amostra carimbada com a hora de chegada",
                        )
                    if "amostra_ms" not in payload:
                        payload["amostra_ms"] = 1000  # default

                    # We can reuse normalizar_payload logic but we need to be careful about exceptions
                    # For now, let's just try to persist it as a device event if we can't fully validate

                    persistido = False
                    try:
                        evento = normalizar_payload(payload, device_header=device_id)
                        evento_dict = evento.model_dump(mode="python")

                        # Try to resolve patient (falha benigna: cai no raw abaixo)
                        if not evento.paciente_id:
                            try:
                                ts_ms = int(evento.ts_utc.timestamp() * 1000)
                                pid = resolver_paciente_por_device_em(DB_PATH, evento.device_id, ts_ms)
                                if pid:
                                    evento.paciente_id = pid
                                    evento_dict["paciente_id"] = pid
                            except Exception:
                                logger.warning(
                                    "resolver_paciente_falhou", device_id=evento.device_id, exc_info=True
                                )

                        if evento.paciente_id:
                            # Full processing
                            registrar_evento(evento)
                        else:
                            # Store raw
                            ts_iso = evento.ts_utc.strftime("%Y-%m-%dT%H:%M:%S")
                            ts_ms = int(evento.ts_utc.timestamp() * 1000)
                            inserir_device_event(DB_PATH, evento.device_id, ts_iso, ts_ms, evento_dict)
                        persistido = True

                    except Exception as e:
                        # Validação falhou. O fallback abaixo era prometido num
                        # comentário mas nunca existiu: o evento era descartado e
                        # mesmo assim recebia ACK "ok", então o device o dava por
                        # entregue e a amostra sumia.
                        logger.warning("ws_event_validation_failed", error=str(e))
                        try:
                            # O timestamp da MEDICAO, nao o da chegada.
                            #
                            # Aqui se usava `datetime.now()`, e isso desfazia a
                            # correcao da reconciliacao: ela resolve o dono da
                            # leitura pelo `ts_ms` do evento orfao. Com a hora de
                            # chegada no lugar da hora da medicao, uma amostra
                            # medida as 02:00 e recebida as 06:00 seria atribuida
                            # a quem ocupava o leito as 06:00 — exatamente o
                            # defeito que a resolucao por tempo eliminou.
                            #
                            # `payload["ts_utc"]` sempre existe neste ponto (o
                            # bloco acima o preenche), entao o `now` so aparece
                            # se nem isso for legivel.
                            ts_evento = _ts_da_medicao(payload, device_id)
                            ts_iso = ts_evento.strftime("%Y-%m-%dT%H:%M:%S")
                            ts_ms = int(ts_evento.replace(tzinfo=timezone.utc).timestamp() * 1000)
                            inserir_device_event(DB_PATH, device_id, ts_iso, ts_ms, payload)
                            persistido = True
                        except Exception:
                            logger.exception("ws_event_nao_persistido", device_id=device_id)

                    # ACK só quando a amostra está realmente guardada; caso
                    # contrário o device precisa saber para reenviar.
                    if seq is not None:
                        if persistido:
                            await websocket.send_json({"status": "ok", "seq": seq})
                        else:
                            await websocket.send_json(
                                {"status": "error", "seq": seq, "error": "persist_failed"}
                            )

                except Exception as e:
                    logger.error("ws_processing_error", error=str(e))
                    # Codigo estavel, nao o texto da excecao: o firmware decide
                    # o que fazer a partir dele, e `str(e)` muda a cada refactor
                    # alem de expor detalhe interno. O motivo real fica no log.
                    await websocket.send_json({"status": "error", "error": "processing_failed"})

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("ws_loop_error", error=str(e))
                break

    except Exception as e:
        logger.error("ws_connection_error", error=str(e))
        try:
            await websocket.close()
        except Exception:
            pass
