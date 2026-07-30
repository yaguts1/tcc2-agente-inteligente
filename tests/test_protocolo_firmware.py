"""Protocolo do firmware ESP32, exercitado contra o backend de verdade.

O QUE ESTE ARQUIVO PROVA — E O QUE NÃO PROVA
--------------------------------------------
Não testa o C++ compilado. Isso continua exigindo gravar num dispositivo (os
testes de compilação e de lógica pura ficam em `firmware/`, ver
`pio test -d firmware`).

O que ele cobre são as duas coisas que o firmware não consegue verificar
sozinho:

1. **O contrato.** Cada resposta que o firmware interpreta — o formato de
   `/api/pacientes/cama/{cama}`, o 422 que dispara descarte definitivo, o
   `{"status":"ok","seq":N}` do WebSocket — é afirmada aqui. Se alguém mexer no
   servidor e quebrar uma dessas suposições, isto falha, em vez de o defeito
   aparecer num ESP32 numa enfermaria.

2. **A máquina de estados.** O algoritmo do firmware (ler, enviar, esperar ACK,
   avançar checkpoint só com confirmação, backoff, retomar do checkpoint) é
   reimplementado aqui em Python e submetido a queda de servidor e reboot. Não
   é o mesmo código, mas é a mesma regra — e é exatamente onde estavam os dois
   piores defeitos do firmware WebSocket. `TestOsDefeitosReaisSeriamPegos`
   mostra que estes testes reprovam a versão antiga do algoritmo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from interface.dao import criar_paciente


# ---------------------------------------------------------------------------
# O dispositivo, como o firmware o define
# ---------------------------------------------------------------------------
class FalhaDeRede(Exception):
    """O envio nem chegou ao servidor (no firmware: `status < 0`)."""


@dataclass
class DispositivoSimulado:
    """Reimplementa o algoritmo de `firmware/esp32_replay`.

    Espelha `processarReplay()` e `confirmarEventoAtual()`: o checkpoint guarda
    o offset ENTREGUE, nunca a posição lida, e só avança com ACK ou recusa
    definitiva.

    `checkpoint_na_leitura=True` reproduz o defeito que a variante WebSocket
    tinha, para os testes poderem demonstrar que o pegam.
    """

    linhas: list[str]
    checkpoint_na_leitura: bool = False
    tentativas_max: int = 0  # 0 = infinito, o padrão do firmware

    offset_confirmado: int = 0
    entregues: list[dict] = field(default_factory=list)
    descartados: int = 0
    tentativas_gastas: int = 0

    async def replay(self, enviar) -> None:
        """Percorre o arquivo a partir do checkpoint.

        `enviar(payload) -> "ack" | "permanente"`, ou levanta `FalhaDeRede`
        para o que o firmware trata como TRANSIENTE.
        """
        indice = self.offset_confirmado
        while indice < len(self.linhas):
            payload = json.loads(self.linhas[indice])
            # Onde o defeito morava: avançar aqui trata "li" como "entreguei".
            if self.checkpoint_na_leitura:
                self.offset_confirmado = indice + 1

            tentativa = 0
            while True:
                try:
                    desfecho = await enviar(payload)
                except FalhaDeRede:
                    self.tentativas_gastas += 1
                    tentativa += 1
                    # `tentativasMax == 0` = insistir para sempre. O backoff
                    # tem teto, então isso é bater no servidor de tempos em
                    # tempos até ele voltar — não desistir da amostra.
                    if self.tentativas_max and tentativa + 1 > self.tentativas_max:
                        return  # evento preservado para a próxima execução
                    continue

                if desfecho == "permanente":
                    # O servidor nunca vai aceitar este conteúdo. Insistir
                    # travaria a fila inteira atrás dele — pula, mas conta.
                    self.descartados += 1
                else:
                    self.entregues.append(payload)
                break

            if not self.checkpoint_na_leitura:
                self.offset_confirmado = indice + 1
            indice += 1


def _amostra(seq: int, paciente: str, cama: str, minuto: int) -> str:
    return json.dumps(
        {
            "device_id": "ESP-PROTO",
            "paciente_id": paciente,
            "cama_id": cama,
            "postura": "supino" if seq % 2 else "lateral_direito",
            "confianca": 0.9,
            "amostra_ms": 300000,
            "ts_utc": f"2026-09-01T10:{minuto:02d}:00Z",
        }
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture()
async def dispositivo(app_isolado):
    """Cliente HTTP sem sessão: a ingestão autentica por token de dispositivo,
    que o conftest deixa desconfigurado."""
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield {"http": c, "db_path": app_isolado.db_path, "app": app_isolado.app}


# ---------------------------------------------------------------------------
# 1) Contrato: o servidor responde o que o firmware interpreta
# ---------------------------------------------------------------------------
class TestContratoQueOFirmwareAssume:
    @pytest.mark.asyncio
    async def test_cama_devolve_paciente_e_perfil(self, dispositivo):
        """`transporteObterPaciente` lê exatamente estes dois campos.

        Sem `paciente_id` o firmware não sai do estado OCIOSO — ele se recusa a
        enviar amostra que não sabe de quem é.
        """
        criar_paciente(dispositivo["db_path"], "Paciente Proto", "alto", cama_id="C-PROTO")

        resp = await dispositivo["http"].get("/api/pacientes/cama/C-PROTO")

        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["paciente_id"], "o firmware aborta sem este campo"
        assert "perfil" in corpo

    @pytest.mark.asyncio
    async def test_cama_vazia_devolve_404(self, dispositivo):
        """404 mantém o firmware tentando; um 2xx com corpo vazio o faria
        enviar amostras sem dono."""
        resp = await dispositivo["http"].get("/api/pacientes/cama/C-VAZIA")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_amostra_valida_recebe_2xx(self, dispositivo):
        ficha = criar_paciente(dispositivo["db_path"], "Proto", "alto", cama_id="C-OK")
        resp = await dispositivo["http"].post(
            "/api/eventos", json=json.loads(_amostra(1, ficha["paciente_id"], "C-OK", 0))
        )
        assert 200 <= resp.status_code < 300

    @pytest.mark.asyncio
    async def test_amostra_malformada_recebe_422(self, dispositivo):
        """422 é o que o firmware classifica como PERMANENTE e pula.

        Se o servidor passasse a devolver 500 aqui, o firmware insistiria para
        sempre numa linha que nunca será aceita — e a fila inteira travaria
        atrás dela.
        """
        resp = await dispositivo["http"].post(
            "/api/eventos", json={"device_id": "ESP-PROTO", "postura": "supino"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_confianca_fora_da_faixa_tambem_e_422(self, dispositivo):
        resp = await dispositivo["http"].post(
            "/api/eventos",
            json={
                "device_id": "ESP-PROTO",
                "paciente_id": "PAC-X",
                "cama_id": "C-X",
                "postura": "supino",
                "confianca": 9.9,
                "amostra_ms": 300000,
                "ts_utc": "2026-09-01T10:00:00Z",
            },
        )
        assert resp.status_code == 422

    def test_websocket_confirma_com_o_seq(self, app_isolado):
        """O ACK precisa devolver `seq` — é assim que o firmware sabe QUAL
        amostra foi confirmada antes de mover o checkpoint."""
        with TestClient(app_isolado.app) as client, client.websocket_connect("/api/ws/eventos") as ws:
            ws.send_json({"device_id": "ESP-PROTO", "cama_id": "C-WS"})
            assert ws.receive_json()["status"] == "connected"
            ws.send_json({**json.loads(_amostra(1, "PAC-WS", "C-WS", 0)), "seq": 12})
            assert ws.receive_json() == {"status": "ok", "seq": 12}

    def test_websocket_erro_traz_codigo_estavel(self, app_isolado):
        """O firmware decide insistir ou desistir a partir do CÓDIGO.

        Se virasse texto livre (`str(e)`), qualquer refactor do servidor mudaria
        a decisão do dispositivo sem ninguém perceber.
        """
        with TestClient(app_isolado.app) as client, client.websocket_connect("/api/ws/eventos") as ws:
            ws.send_json({"device_id": "ESP-PROTO", "cama_id": "C-WS"})
            ws.receive_json()
            ws.send_text("isto nao e json")
            resposta = ws.receive_json()

        assert resposta["status"] == "error"
        assert isinstance(resposta.get("error"), str) and resposta["error"]


# ---------------------------------------------------------------------------
# 2) Máquina de estados: nenhuma amostra se perde
# ---------------------------------------------------------------------------
class TestResilienciaDoReplay:
    async def _enviar_real(self, cliente, payload):
        resp = await cliente.post("/api/eventos", json=payload)
        if resp.status_code == 422:
            return "permanente"
        if resp.status_code >= 500:
            raise FalhaDeRede()
        return "ack"

    @pytest.mark.asyncio
    async def test_arquivo_inteiro_chega_ao_banco(self, dispositivo):
        import sqlite3

        ficha = criar_paciente(dispositivo["db_path"], "Proto", "alto", cama_id="C-FULL")
        pid = ficha["paciente_id"]
        linhas = [_amostra(i, pid, "C-FULL", i) for i in range(5)]
        dev = DispositivoSimulado(linhas=linhas)

        await dev.replay(lambda p: self._enviar_real(dispositivo["http"], p))

        assert len(dev.entregues) == 5
        with sqlite3.connect(dispositivo["db_path"]) as conn:
            gravadas = conn.execute(
                "SELECT COUNT(*) FROM grade WHERE paciente_id = ?", (pid,)
            ).fetchone()[0]
        assert gravadas == 5, "toda amostra confirmada precisa estar no banco"

    @pytest.mark.asyncio
    async def test_queda_de_servidor_nao_perde_amostra(self, dispositivo):
        """O caso que motiva o backoff infinito.

        O servidor cai no meio do arquivo e volta. Nenhuma amostra pode se
        perder e nenhuma pode ser duplicada.
        """
        ficha = criar_paciente(dispositivo["db_path"], "Proto", "alto", cama_id="C-QUEDA")
        pid = ficha["paciente_id"]
        linhas = [_amostra(i, pid, "C-QUEDA", i) for i in range(6)]
        dev = DispositivoSimulado(linhas=linhas)

        fora_do_ar = {"restantes": 4}  # falha as 4 primeiras tentativas da 3ª amostra

        async def enviar(payload):
            if len(dev.entregues) == 3 and fora_do_ar["restantes"] > 0:
                fora_do_ar["restantes"] -= 1
                raise FalhaDeRede()
            return await self._enviar_real(dispositivo["http"], payload)

        await dev.replay(enviar)

        assert len(dev.entregues) == 6, "a queda não pode custar amostra"
        assert dev.tentativas_gastas == 4, "o firmware insiste, não desiste"
        enviadas = [p["ts_utc"] for p in dev.entregues]
        assert len(set(enviadas)) == 6, "e não pode duplicar"

    @pytest.mark.asyncio
    async def test_reboot_retoma_da_amostra_certa(self, dispositivo):
        """O defeito mais grave da variante WebSocket.

        O checkpoint guardava a posição LIDA. Ao reiniciar, o replay retomava
        DEPOIS do evento que nunca chegou — perdendo em silêncio justamente a
        amostra que falhou.
        """
        ficha = criar_paciente(dispositivo["db_path"], "Proto", "alto", cama_id="C-REBOOT")
        pid = ficha["paciente_id"]
        linhas = [_amostra(i, pid, "C-REBOOT", i) for i in range(5)]

        # Primeira execução: o link cai na 3ª amostra e o dispositivo desiste
        # (tentativasMax finito, para simular o desligamento).
        dev = DispositivoSimulado(linhas=linhas, tentativas_max=2)

        async def cai_na_terceira(payload):
            if len(dev.entregues) == 2:
                raise FalhaDeRede()
            return await self._enviar_real(dispositivo["http"], payload)

        await dev.replay(cai_na_terceira)
        assert len(dev.entregues) == 2
        assert dev.offset_confirmado == 2, "o checkpoint não pode passar da amostra não entregue"

        # Reboot: novo dispositivo, mesmo checkpoint.
        depois = DispositivoSimulado(linhas=linhas)
        depois.offset_confirmado = dev.offset_confirmado
        await depois.replay(lambda p: self._enviar_real(dispositivo["http"], p))

        assert len(depois.entregues) == 3
        # O conjunto entregue nas duas execuções cobre o arquivo inteiro.
        todas = [p["ts_utc"] for p in dev.entregues + depois.entregues]
        assert sorted(todas) == sorted(json.loads(linha)["ts_utc"] for linha in linhas)

    @pytest.mark.asyncio
    async def test_linha_recusada_nao_trava_a_fila(self, dispositivo):
        """422 no meio do arquivo: pula a linha, entrega o resto, conta o descarte."""
        ficha = criar_paciente(dispositivo["db_path"], "Proto", "alto", cama_id="C-422")
        pid = ficha["paciente_id"]
        linhas = [
            _amostra(0, pid, "C-422", 0),
            json.dumps({"device_id": "ESP-PROTO", "postura": "supino"}),  # inválida
            _amostra(2, pid, "C-422", 2),
        ]
        dev = DispositivoSimulado(linhas=linhas)

        await dev.replay(lambda p: self._enviar_real(dispositivo["http"], p))

        assert len(dev.entregues) == 2
        assert dev.descartados == 1, "o descarte precisa ser contado, não ficar invisível"
        assert dev.offset_confirmado == 3, "a fila segue depois da linha recusada"


# ---------------------------------------------------------------------------
# 3) Estes testes teriam pego os defeitos reais?
# ---------------------------------------------------------------------------
class TestOsDefeitosReaisSeriamPegos:
    """Um teste de regressão que nunca reprovou a versão com defeito não
    demonstra nada. Aqui o algoritmo antigo é reexecutado de propósito."""

    async def _enviar(self, cliente, payload):
        resp = await cliente.post("/api/eventos", json=payload)
        if resp.status_code == 422:
            return "permanente"
        return "ack"

    @pytest.mark.asyncio
    async def test_checkpoint_na_leitura_perde_a_amostra_que_falhou(self, dispositivo):
        ficha = criar_paciente(dispositivo["db_path"], "Proto", "alto", cama_id="C-BUG")
        pid = ficha["paciente_id"]
        linhas = [_amostra(i, pid, "C-BUG", i) for i in range(5)]

        # `checkpoint_na_leitura=True` é o comportamento da variante WebSocket.
        dev = DispositivoSimulado(linhas=linhas, checkpoint_na_leitura=True, tentativas_max=2)

        async def cai_na_terceira(payload):
            if len(dev.entregues) == 2:
                raise FalhaDeRede()
            return await self._enviar(dispositivo["http"], payload)

        await dev.replay(cai_na_terceira)

        # O checkpoint passou da amostra que NÃO foi entregue.
        assert dev.offset_confirmado == 3, "reproduzindo o defeito antigo"
        assert len(dev.entregues) == 2

        depois = DispositivoSimulado(linhas=linhas)
        depois.offset_confirmado = dev.offset_confirmado
        await depois.replay(lambda p: self._enviar(dispositivo["http"], p))

        entregues = [p["ts_utc"] for p in dev.entregues + depois.entregues]
        esperadas = [json.loads(linha)["ts_utc"] for linha in linhas]
        perdidas = set(esperadas) - set(entregues)

        assert perdidas, "o defeito deveria perder pelo menos uma amostra"
        assert len(perdidas) == 1
        # A perdida é exatamente a que estava sendo enviada quando o link caiu.
        assert perdidas == {json.loads(linhas[2])["ts_utc"]}

    @pytest.mark.asyncio
    async def test_limite_baixo_de_tentativas_encerra_o_replay(self, dispositivo):
        """A variante WebSocket usava `tentativasMax = 5`.

        Com backoff exponencial isso soma ~16 s: qualquer reinício de servidor
        mais longo parava o replay DE VEZ. Com o padrão (infinito), a mesma
        indisponibilidade só atrasa.
        """
        ficha = criar_paciente(dispositivo["db_path"], "Proto", "alto", cama_id="C-LIM")
        pid = ficha["paciente_id"]
        linhas = [_amostra(i, pid, "C-LIM", i) for i in range(3)]

        indisponivel = {"restantes": 10}

        async def instavel(payload):
            if indisponivel["restantes"] > 0:
                indisponivel["restantes"] -= 1
                raise FalhaDeRede()
            return await self._enviar(dispositivo["http"], payload)

        com_limite = DispositivoSimulado(linhas=linhas, tentativas_max=5)
        await com_limite.replay(instavel)
        assert com_limite.entregues == [], "com limite baixo, desiste e não entrega nada"

        indisponivel["restantes"] = 10
        infinito = DispositivoSimulado(linhas=linhas)  # tentativas_max=0
        await infinito.replay(instavel)
        assert len(infinito.entregues) == 3, "insistindo, a indisponibilidade só atrasa"
