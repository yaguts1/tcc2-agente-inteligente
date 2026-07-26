"""O corte por `limit` em /frontend/alerts precisa ser visivel.

O dashboard filtra em MEMORIA sobre o que recebeu: o que a resposta cortou nao
existe para o filtro da tela. Uma lista de N alertas com `limit=N` e
indistinguivel de "existem exatamente N", entao um paciente atrasado ficaria
fora sem nenhum sinal — a mesma familia do relatorio truncado da exportacao.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.dao import criar_paciente, inserir_alertas


@pytest_asyncio.fixture()
async def client(app_isolado, cabecalho_auth):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth()
    ) as c:
        yield {"client": c, "db_path": app_isolado.db_path}


def _criar_alertas(db_path: str, quantidade: int) -> None:
    ficha = criar_paciente(db_path, "Paciente Cheio", "alto", cama_id="Q9-L9")
    pid = ficha["paciente_id"]
    inserir_alertas(
        db_path,
        [
            {
                "paciente_id": pid,
                # Minutos distintos: `alertas` tem PK (paciente_id, inicio).
                "inicio": f"2026-06-01T10:{i:02d}:00",
                "fim": None,
                "tipo": "imobilidade",
                "perfil": "alto",
                "janela_min": 120,
                "status": "aberto",
                "duracao_min": 130,
            }
            for i in range(quantidade)
        ],
    )


@pytest.mark.asyncio
async def test_header_informa_o_total_quando_a_lista_e_cortada(client):
    """`X-Total-Count` traz o total dos filtros, nao o tamanho da pagina."""
    _criar_alertas(client["db_path"], 5)

    resp = await client["client"].get("/api/frontend/alerts?horas=100000&limit=3")

    assert resp.status_code == 200
    assert len(resp.json()) == 3
    assert resp.headers["X-Total-Count"] == "5", (
        "sem o total, 3 alertas com limit=3 sao indistinguiveis de 'existem 3'"
    )


@pytest.mark.asyncio
async def test_header_bate_com_a_lista_quando_nao_ha_corte(client):
    """Lista completa: total igual ao tamanho, para o cliente nao avisar a toa."""
    _criar_alertas(client["db_path"], 4)

    resp = await client["client"].get("/api/frontend/alerts?horas=100000&limit=50")

    assert len(resp.json()) == 4
    assert resp.headers["X-Total-Count"] == "4"


@pytest.mark.asyncio
async def test_total_respeita_os_filtros(client):
    """O total e dos que casam com o filtro, nao de todos os alertas do banco."""
    _criar_alertas(client["db_path"], 5)

    # `perfil=alto` -> riskLevel `high`; nenhum alerta e `low`.
    resp = await client["client"].get("/api/frontend/alerts?horas=100000&riskLevel=low")

    assert resp.json() == []
    assert resp.headers["X-Total-Count"] == "0"


@pytest.mark.asyncio
async def test_cache_preserva_o_total(client):
    """A segunda chamada vem do cache de 30s e nao pode perder o total."""
    _criar_alertas(client["db_path"], 5)
    url = "/api/frontend/alerts?horas=100000&limit=2"

    primeira = await client["client"].get(url)
    segunda = await client["client"].get(url)

    assert primeira.headers["X-Total-Count"] == "5"
    assert segunda.headers["X-Total-Count"] == "5"
    assert primeira.json() == segunda.json()
