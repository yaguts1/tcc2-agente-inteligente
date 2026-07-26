"""Painel de eventos orfaos: o numero que a tela exibe precisa ser alcancavel.

`interface/routers/devices.py` era o modulo com a pior cobertura do projeto
(33%), e o `total_orphans` que a tela de admin mostra como "N eventos
aguardando reconciliacao" era `len(events)` — a contagem da amostra JA
limitada, incluindo eventos que nenhum botao daquela tela resolve.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.dao import criar_paciente
from interface.repositories.devices import inserir_device_event


@pytest_asyncio.fixture()
async def client(app_isolado, cabecalho_auth):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth()
    ) as c:
        yield {"client": c, "db_path": app_isolado.db_path}


def _orfao(db_path: str, device: str, ts_ms: int, cama_id: str | None) -> None:
    payload = {"device_id": device, "postura": "supino", "confianca": 0.9}
    if cama_id is not None:
        payload["cama_id"] = cama_id
    inserir_device_event(db_path, device, "2026-06-01T10:00:00", ts_ms, payload)


class TestTotalAlcancavel:
    @pytest.mark.asyncio
    async def test_evento_sem_leito_e_contado_a_parte(self, client):
        """O operador precisa saber que aquele resto nao sai pelos botoes.

        Antes, eventos sem `cama_id` entravam no `total_orphans` e nao
        apareciam em leito nenhum: reconciliar TODOS os leitos deixava o
        contador parado, sem nada explicando o motivo.
        """
        db_path = client["db_path"]
        _orfao(db_path, "ESP-A", 1, "C01")
        _orfao(db_path, "ESP-B", 2, None)
        _orfao(db_path, "ESP-C", 3, None)

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        assert corpo["total_orphans"] == 3
        assert corpo["orfaos_com_leito"] == 1
        assert corpo["orfaos_sem_leito"] == 2

    @pytest.mark.asyncio
    async def test_com_leito_soma_exatamente_os_leitos(self, client):
        """A soma dos leitos e o que a tela consegue resolver clicando."""
        db_path = client["db_path"]
        for i in range(3):
            _orfao(db_path, "ESP-A", i + 1, "C01")
        for i in range(2):
            _orfao(db_path, "ESP-B", i + 10, "C02")

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        assert corpo["orfaos_com_leito"] == sum(b["count"] for b in corpo["beds"])
        assert corpo["orfaos_com_leito"] == 5
        assert corpo["orfaos_sem_leito"] == 0

    @pytest.mark.asyncio
    async def test_total_nao_para_de_crescer_no_teto_da_amostra(self, client, monkeypatch):
        """Num painel que existe para diagnosticar ACUMULO, o total nao pode
        empacar no limite da consulta — seria parar de contar exatamente
        quando o problema fica grave."""
        import interface.routers.devices as devices

        monkeypatch.setattr(devices, "LIMITE_AMOSTRA_STATS", 2)
        db_path = client["db_path"]
        for i in range(5):
            _orfao(db_path, "ESP-A", i + 1, "C01")

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        assert corpo["total_orphans"] == 5, "o total vem de COUNT(*), nao da amostra"
        assert corpo["amostra_truncada"] is True

    @pytest.mark.asyncio
    async def test_sem_truncamento_a_flag_e_falsa(self, client):
        """Para a tela nao avisar de corte que nao houve."""
        _orfao(client["db_path"], "ESP-A", 1, "C01")

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        assert corpo["amostra_truncada"] is False


class TestAgrupamentoPorLeito:
    @pytest.mark.asyncio
    async def test_resolve_o_paciente_atual_do_leito(self, client):
        db_path = client["db_path"]
        ficha = criar_paciente(db_path, "Maria Souza", "alto", cama_id="C01")
        _orfao(db_path, "ESP-A", 1, "C01")

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        leito = corpo["beds"][0]
        assert leito["current_patient"]["id"] == ficha["paciente_id"]
        assert leito["current_patient"]["name"] == "Maria Souza"

    @pytest.mark.asyncio
    async def test_leito_vazio_fica_sem_paciente(self, client):
        _orfao(client["db_path"], "ESP-A", 1, "C99")

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        assert corpo["beds"][0]["current_patient"] is None

    @pytest.mark.asyncio
    async def test_ordena_do_leito_com_mais_eventos_para_o_menor(self, client):
        db_path = client["db_path"]
        _orfao(db_path, "ESP-A", 1, "C01")
        for i in range(3):
            _orfao(db_path, "ESP-B", i + 10, "C02")

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        assert [b["cama_id"] for b in corpo["beds"]] == ["C02", "C01"]

    @pytest.mark.asyncio
    async def test_primeiro_e_ultimo_evento_do_leito(self, client):
        db_path = client["db_path"]
        payload = {"device_id": "ESP-A", "cama_id": "C01", "postura": "supino"}
        inserir_device_event(db_path, "ESP-A", "2026-06-01T08:00:00", 1, payload)
        inserir_device_event(db_path, "ESP-A", "2026-06-01T12:00:00", 2, payload)

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        leito = corpo["beds"][0]
        assert leito["first_event"] == "2026-06-01T08:00:00"
        assert leito["last_event"] == "2026-06-01T12:00:00"


class TestEventoJaProcessado:
    @pytest.mark.asyncio
    async def test_orfao_reconciliado_sai_da_conta(self, client):
        """`processed_at` preenchido significa resolvido; contar de novo faria
        a tela pedir acao sobre o que ja foi feito."""
        db_path = client["db_path"]
        _orfao(db_path, "ESP-A", 1, "C01")
        _orfao(db_path, "ESP-A", 2, "C01")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE device_events SET processed_at = ? WHERE ts_ms = ?",
                ("2026-06-01T11:00:00", 1),
            )
            conn.commit()

        corpo = (await client["client"].get("/api/device_events/stats")).json()

        assert corpo["total_orphans"] == 1
        assert corpo["orfaos_com_leito"] == 1


class TestOutrasRotasDeDevices:
    @pytest.mark.asyncio
    async def test_listagem_de_eventos_filtra_por_dispositivo(self, client):
        db_path = client["db_path"]
        _orfao(db_path, "ESP-A", 1, "C01")
        _orfao(db_path, "ESP-B", 2, "C02")

        corpo = (await client["client"].get("/api/device_events?device_id=ESP-A")).json()

        assert [e["device_id"] for e in corpo] == ["ESP-A"]

    @pytest.mark.asyncio
    async def test_registro_de_dispositivo_aparece_na_listagem(self, client):
        resp = await client["client"].post(
            "/api/devices/register", json={"device_id": "ESP-NOVO", "meta": {"cama_id": "C7"}}
        )
        assert resp.status_code == 201

        devices = (await client["client"].get("/api/devices")).json()
        assert any(d["device_id"] == "ESP-NOVO" for d in devices)

    @pytest.mark.asyncio
    async def test_rotas_de_devices_exigem_sessao(self, app_isolado):
        """Payload de sensor e leito sao dados clinicos identificaveis."""
        transport = ASGITransport(app=app_isolado.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as anon:
            for rota in ("/api/devices", "/api/device_events", "/api/device_events/stats"):
                assert (await anon.get(rota)).status_code == 401, rota


class TestPayloadIlegivel:
    @pytest.mark.asyncio
    async def test_payload_corrompido_nao_derruba_o_painel(self, client):
        """O painel e a ferramenta de diagnostico: derrubar tudo por uma linha
        ruim tiraria a visibilidade justamente quando ha algo errado."""
        db_path = client["db_path"]
        _orfao(db_path, "ESP-A", 1, "C01")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO device_events (device_id, ts, ts_ms, payload) VALUES (?, ?, ?, ?)",
                ("ESP-B", "2026-06-01T10:00:00", 2, "{isto nao e json"),
            )
            conn.commit()

        resp = await client["client"].get("/api/device_events/stats")

        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["total_orphans"] == 2
        # O ilegivel nao vira leito, mas continua contado como pendente.
        assert corpo["orfaos_com_leito"] == 1
        assert corpo["orfaos_sem_leito"] == 1

    @pytest.mark.asyncio
    async def test_payload_valido_e_lido_como_json(self, client):
        db_path = client["db_path"]
        _orfao(db_path, "ESP-A", 1, "C01")

        corpo = (await client["client"].get("/api/device_events")).json()

        assert json.loads(json.dumps(corpo[0]["payload"]))["cama_id"] == "C01"
