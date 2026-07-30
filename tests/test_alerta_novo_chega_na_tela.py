"""O alerta que manda virar o paciente precisa chegar a tela.

Tres camadas independentes impediam isso, e bastava uma:

1. NADA anunciava alerta novo. `broadcast` so era chamado por reconhecer e
   completar — nunca pelo motor ao ABRIR um alerta. O docstring da rota
   /ws/alerts afirmava o contrario ("New alerts will be pushed").
2. O frontend desligava o polling enquanto o WS estivesse conectado
   (`enabled: !wsConnected`), tratando conexao aberta como garantia de que as
   mensagens chegam.
3. O handler do WS fazia `prev.map`, que atualiza item existente e nao insere.
   Mesmo com o anuncio, o alerta novo nao entraria na lista.

Somados: com a tela conectada, a lista congelava no que existia quando a
pagina abriu, e nada indicava isso.
"""

import asyncio
import threading

import pytest

from interface.services.alerts_service import (
    agendar_anuncio,
    montar_payload_alerta_novo,
    registrar_loop,
)

ALERTA = {
    "paciente_id": "PAC-WS",
    "inicio": "2026-07-26T05:40:29",
    "tipo": "imobilidade",
    "perfil": "alto",
    "status": "aberto",
    "janela_min": 60,
}


def test_payload_carrega_os_campos_que_o_filtro_usa():
    """`severity`, `patient_id` e `alert_type` sao os campos contra os quais o
    WebSocketFilter casa. Sem eles, cliente com filtro nunca recebe nada."""
    payload = montar_payload_alerta_novo("PAC-WS", ALERTA)

    assert payload["type"] == "alert_new"
    assert payload["alert_id"] == "PAC-WS__2026-07-26T05:40:29"
    assert payload["status"] == "pending"
    assert payload["patient_id"] == "PAC-WS"
    assert payload["severity"] == "high"
    assert payload["alert_type"] == "imobilidade"


def test_tipo_distingue_alerta_novo_de_mudanca_de_status():
    """Sao reacoes diferentes na tela: inserir na lista vs. atualizar uma linha."""
    from interface.services.alerts_service import _montar_payload_broadcast

    assert montar_payload_alerta_novo("PAC-WS", ALERTA)["type"] == "alert_new"
    assert _montar_payload_broadcast("PAC-WS__x", "PAC-WS", "acknowledged")["type"] == "alert_update"


@pytest.mark.asyncio
async def test_anuncio_funciona_a_partir_de_outra_thread(monkeypatch):
    """A ingestao HTTP e um handler `def`: roda no threadpool, fora do loop.

    `asyncio.get_running_loop()` levanta RuntimeError la, entao um agendamento
    que so use `create_task` nao anuncia nada no caminho principal — o do
    sensor real. Este teste roda o agendamento de uma thread, como acontece de
    verdade.
    """
    import interface.services.alerts_service as svc

    publicados: list[dict] = []

    class ManagerFalso:
        async def broadcast(self, payload):
            publicados.append(payload)

    monkeypatch.setattr(svc, "ws_manager_optimized", ManagerFalso())
    registrar_loop(asyncio.get_running_loop())

    erro: list[BaseException] = []

    def de_outra_thread():
        try:
            agendar_anuncio([ALERTA])
        except BaseException as exc:  # noqa: BLE001 - propagado para o assert
            erro.append(exc)

    t = threading.Thread(target=de_outra_thread)
    t.start()
    t.join()
    await asyncio.sleep(0.2)

    assert not erro, erro
    assert len(publicados) == 1, "o alerta aberto no threadpool nao chegou ao WS"
    assert publicados[0]["alert_id"] == "PAC-WS__2026-07-26T05:40:29"


@pytest.mark.asyncio
async def test_anuncio_invalida_o_cache_da_listagem(monkeypatch):
    """A mensagem dispara um refetch; se o cache de 30s nao for limpo, o
    refetch devolve a lista velha, ainda SEM o alerta novo — a tela receberia
    o aviso e continuaria mostrando o estado anterior."""
    import interface.services.alerts_service as svc

    class ManagerFalso:
        async def broadcast(self, payload):
            pass

    monkeypatch.setattr(svc, "ws_manager_optimized", ManagerFalso())
    await svc.api_cache.set("alerts:24:None:None:None:100:0", ["lista velha"])

    await svc.anunciar_alertas_novos([ALERTA])

    assert await svc.api_cache.get("alerts:24:None:None:None:100:0") is None


@pytest.mark.asyncio
async def test_sem_alertas_nao_publica_nada(monkeypatch):
    import interface.services.alerts_service as svc

    publicados = []

    class ManagerFalso:
        async def broadcast(self, payload):
            publicados.append(payload)

    monkeypatch.setattr(svc, "ws_manager_optimized", ManagerFalso())
    await svc.anunciar_alertas_novos([])

    assert publicados == []


def test_ingestao_anuncia_o_alerta_que_o_motor_abriu(monkeypatch):
    """O caminho real: `registrar_evento` -> motor abre alerta -> anuncio."""
    import interface.services.ingestao_service as ing

    agendados: list[list[dict]] = []
    monkeypatch.setattr(
        "interface.services.alerts_service.agendar_anuncio",
        lambda alertas: agendados.append(alertas),
    )
    monkeypatch.setattr(ing, "inserir_grade", lambda *a, **k: None)
    monkeypatch.setattr(ing, "inserir_eventos", lambda *a, **k: None)
    monkeypatch.setattr(ing, "inserir_alertas", lambda *a, **k: 1)
    monkeypatch.setattr(
        ing.PROCESSADOR,
        "processar_amostra",
        # `**_` porque a ingestao passa a conexao compartilhada: grade,
        # eventos, estado do motor e alertas gravam numa transacao so.
        # O contrato que este teste protege — o alerta recem-aberto
        # chegar ao anuncio — nao mudou.
        lambda evento, **_: [ALERTA],
    )

    from interface.schemas import EventPayload

    payload = EventPayload.model_validate({
        "device_id": "dev-1",
        "paciente_id": "PAC-WS",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 300000,
        "ts_utc": "2026-07-26T05:40:29",
    })
    ing.registrar_evento(payload)

    assert agendados == [[ALERTA]], "a ingestao nao anunciou o alerta aberto pelo motor"


def test_falha_no_anuncio_nao_derruba_a_ingestao(monkeypatch):
    """A amostra JA foi persistida. Um cliente WS problematico nao pode fazer o
    dispositivo reenviar um dado que o servidor ja tem."""
    import interface.services.ingestao_service as ing

    def explode(_alertas):
        raise RuntimeError("WS fora do ar")

    monkeypatch.setattr("interface.services.alerts_service.agendar_anuncio", explode)
    monkeypatch.setattr(ing, "inserir_grade", lambda *a, **k: None)
    monkeypatch.setattr(ing, "inserir_eventos", lambda *a, **k: None)
    monkeypatch.setattr(ing, "inserir_alertas", lambda *a, **k: 1)
    monkeypatch.setattr(
        ing.PROCESSADOR,
        "processar_amostra",
        # `**_` porque a ingestao passa a conexao compartilhada: grade,
        # eventos, estado do motor e alertas gravam numa transacao so.
        # O contrato que este teste protege — o alerta recem-aberto
        # chegar ao anuncio — nao mudou.
        lambda evento, **_: [ALERTA],
    )

    from interface.schemas import EventPayload

    payload = EventPayload.model_validate({
        "device_id": "dev-1",
        "paciente_id": "PAC-WS",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 300000,
        "ts_utc": "2026-07-26T05:40:29",
    })

    assert ing.registrar_evento(payload) == {"alertas": 1}
