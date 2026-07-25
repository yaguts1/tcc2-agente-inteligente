"""Rate limiting atras do proxy reverso.

Dois defeitos que so aparecem em producao, onde o Caddy fica na frente do app:

1. O limitador usava `request.client.host`. Atras do proxy isso e SEMPRE o IP
   do Caddy, entao todos os usuarios caiam no mesmo balde: bastava um cliente
   errar a senha 5 vezes para bloquear o login de todo mundo.

2. A ingestao chaveava por `X-Device-Id`, header que o proprio cliente escolhe
   — rotacionar o valor dava um balde novo e o limite virava decoracao.

O X-Forwarded-For so pode ser acreditado quando o peer imediato e um proxy
confiavel; senao qualquer cliente forjaria o header para escapar do limite.
"""

import asyncio
import types

import pytest

import interface.api_shared as sh

IP_CADDY = "172.19.0.5"  # rede interna do Docker (privada => proxy confiavel)


def _req(xff: str | None, peer: str = IP_CADDY, device_id: str | None = None):
    headers = {}
    if xff:
        headers["X-Forwarded-For"] = xff
    if device_id:
        headers["X-Device-Id"] = device_id
    return types.SimpleNamespace(
        client=types.SimpleNamespace(host=peer),
        headers=headers,
        state=types.SimpleNamespace(),
    )


def test_usa_forwarded_for_quando_vem_de_proxy_confiavel():
    assert sh.ip_do_cliente(_req("203.0.113.5")) == "203.0.113.5"


def test_ignora_forwarded_for_forjado_de_peer_nao_confiavel():
    """De um peer publico o header e do proprio cliente: acreditar nele
    permitiria escapar do rate limit inventando um IP a cada requisicao."""
    assert sh.ip_do_cliente(_req("1.2.3.4", peer="203.0.113.9")) == "203.0.113.9"


def test_limite_de_login_e_por_cliente_e_nao_global():
    async def cenario():
        sh.rate_limiter.reset()
        # Cliente A esgota as 5 tentativas por minuto.
        for _ in range(5):
            await sh._check_auth_rate_limit(_req("203.0.113.5"))
        with pytest.raises(Exception):
            await sh._check_auth_rate_limit(_req("203.0.113.5"))

        # Cliente B, outro IP atras do MESMO proxy, nao pode estar bloqueado.
        await sh._check_auth_rate_limit(_req("198.51.100.9"))

    asyncio.run(cenario())


def test_ingestao_nao_e_contornavel_rotacionando_device_id():
    async def cenario():
        sh.reset_rate_limiter()
        capacidade = int(sh._TOKEN_BUCKET_CAPACITY)
        for i in range(capacidade + 20):
            try:
                await sh._aplicar_rate_limit(
                    _req("203.0.113.77", device_id=f"ESP32-{i}")
                )
            except Exception:
                return  # bloqueou apesar dos device_ids distintos
        pytest.fail(
            f"{capacidade + 20} requisicoes com device_ids distintos passaram: "
            "o limite voltou a ser chaveado por um valor que o cliente controla"
        )

    asyncio.run(cenario())
