"""O rate limit dos endpoints comuns, que estava definido e nunca aplicado.

`_check_api_rate_limit` existia em api_shared.py e NENHUM endpoint o declarava
como dependencia: alertas, timeline, stats, pacientes e exportacao nao tinham
teto nenhum. So login (5/min), lote (10/min) e ingestao (token bucket) eram
protegidos.
"""

from __future__ import annotations

import importlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture()
async def client(app_isolado, cabecalho_auth):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth()
    ) as c:
        yield c


@pytest.fixture()
def limite_baixo(monkeypatch):
    """Reduz o teto para o teste nao precisar disparar centenas de requisicoes."""
    api_shared = importlib.import_module("interface.api_shared")
    monkeypatch.setenv("API_RATE_LIMIT_POR_MINUTO", "3")
    api_shared.rate_limiter.reset()
    yield 3
    api_shared.rate_limiter.reset()


@pytest.mark.asyncio
async def test_excesso_de_requisicoes_recebe_429(client, limite_baixo):
    """Passado o teto, 429 com Retry-After — e nao 200 indefinidamente."""
    for _ in range(limite_baixo):
        assert (await client.get("/api/stats")).status_code == 200

    excedente = await client.get("/api/stats")

    assert excedente.status_code == 429
    assert excedente.json()["detail"]["code"] == "rate_limited"
    assert "Retry-After" in excedente.headers


@pytest.mark.asyncio
async def test_o_balde_e_compartilhado_entre_os_endpoints_comuns(client, limite_baixo):
    """Um teto por IP, nao um por rota: senao bastaria alternar rotas."""
    assert (await client.get("/api/stats")).status_code == 200
    assert (await client.get("/api/timeline")).status_code == 200
    assert (await client.get("/api/pacientes")).status_code == 200

    assert (await client.get("/api/frontend/alerts")).status_code == 429


@pytest.mark.asyncio
async def test_healthcheck_nunca_e_limitado(client, limite_baixo):
    """`/healthz` e `/api/health` fora do balde, sob qualquer pressao.

    O healthcheck do container bate a cada 30s e o Caddy depende dele. Um 429
    ali faria o proprio monitoramento derrubar o servico que ele vigia — o
    limite viraria a causa da indisponibilidade que deveria evitar.
    """
    for _ in range(limite_baixo + 5):
        await client.get("/api/stats")  # satura o balde

    assert (await client.get("/api/stats")).status_code == 429
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/api/health")).status_code == 200


@pytest.mark.asyncio
async def test_metrics_nunca_e_limitado(client, limite_baixo):
    """Scraping do Prometheus em intervalo fixo nao pode ser recusado."""
    for _ in range(limite_baixo + 5):
        await client.get("/api/stats")

    assert (await client.get("/metrics")).status_code == 200


@pytest.mark.asyncio
async def test_ingestao_nao_usa_o_balde_da_api(client, limite_baixo):
    """O ESP32 tem o proprio token bucket; saturar a API nao pode cala-lo.

    Sao perfis de trafego diferentes: uma enfermaria inteira de sensores
    enviando amostras nao deve competir com os cliques da tela.
    """
    for _ in range(limite_baixo + 5):
        await client.get("/api/stats")
    assert (await client.get("/api/stats")).status_code == 429

    evento = {
        "device_id": "ESP-RL",
        "paciente_id": "PAC-RL",
        "cama_id": "C-RL",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 300000,
        "ts_utc": "2026-05-01T00:00:00Z",
    }
    assert (await client.post("/api/eventos", json=evento)).status_code == 200


@pytest.mark.asyncio
async def test_limite_padrao_e_folgado_para_o_uso_real(client):
    """Sem configuracao, o polling do dashboard nao pode esbarrar no teto.

    O modo de falha de um limite apertado e a tela do leito exibindo erro no
    meio do plantao — pior do que o que o limite previne.
    """
    api_shared = importlib.import_module("interface.api_shared")
    assert api_shared._limite_api_por_minuto() >= 120

    # Uma rajada plausivel (varios alertas abrindo, cada um disparando refetch)
    # tem que passar limpa.
    for _ in range(30):
        assert (await client.get("/api/frontend/alerts")).status_code == 200


def test_valor_invalido_cai_no_padrao(monkeypatch):
    """Configuracao ilegivel nao pode virar teto 0 e bloquear tudo."""
    api_shared = importlib.import_module("interface.api_shared")
    monkeypatch.setenv("API_RATE_LIMIT_POR_MINUTO", "nao-e-numero")
    assert api_shared._limite_api_por_minuto() == 240
