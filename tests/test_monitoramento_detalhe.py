"""/api/monitoramento: QUAIS pacientes estao sem dados, nao so quantos.

`/api/stats` ja trazia a contagem e o dashboard exibia o aviso vermelho
("3 pacientes sem monitoramento — verifique o sensor"). Faltava o detalhe: sem
ele nao havia como descobrir QUAIS leitos conferir sem abrir o log do
servidor. O endpoint existia e nenhuma tela o consumia.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.dao import criar_paciente, inserir_grade
from interface.tempo import agora_utc_naive


@pytest_asyncio.fixture()
async def client(app_isolado, cabecalho_auth):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth()
    ) as c:
        yield {"client": c, "db_path": app_isolado.db_path}


def _com_leitura_agora(db_path: str, nome: str, cama: str) -> str:
    import pandas as pd

    ficha = criar_paciente(db_path, nome, "alto", cama_id=cama)
    agora = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")
    inserir_grade(
        db_path,
        pd.DataFrame([{"timestamp": agora, "postura": "supino", "confianca": 0.9}]),
        ficha["paciente_id"],
    )
    return ficha["paciente_id"]


@pytest.mark.asyncio
async def test_lista_quem_nunca_recebeu_leitura(client):
    """`nunca_recebeu_dados` separa instalacao errada de sensor que parou.

    A acao corretiva e diferente: um pede trocar/religar o sensor, o outro
    pede conferir o vinculo device<->leito.
    """
    ficha = criar_paciente(client["db_path"], "Sem Sensor", "alto", cama_id="Q1-L1")

    resp = await client["client"].get("/api/monitoramento")

    assert resp.status_code == 200
    corpo = resp.json()
    sem = corpo["pacientes_sem_monitoramento"]

    assert corpo["sem_monitoramento"] == 1
    assert len(sem) == 1
    assert sem[0]["paciente_id"] == ficha["paciente_id"]
    assert sem[0]["nome"] == "Sem Sensor"
    assert sem[0]["cama_id"] == "Q1-L1"
    assert sem[0]["nunca_recebeu_dados"] is True


@pytest.mark.asyncio
async def test_paciente_com_leitura_recente_fica_de_fora(client):
    """A lista e de quem precisa de acao — incluir quem esta bem seria ruido."""
    pid = _com_leitura_agora(client["db_path"], "Monitorado", "Q2-L2")

    corpo = (await client["client"].get("/api/monitoramento")).json()

    assert corpo["sem_monitoramento"] == 0
    assert corpo["pacientes_sem_monitoramento"] == []
    assert any(p["paciente_id"] == pid and p["monitorado"] for p in corpo["pacientes"])


@pytest.mark.asyncio
async def test_contagem_bate_com_a_de_stats(client):
    """O aviso do dashboard vem de /stats e a lista de /monitoramento.

    Se os dois numeros divergirem, a tela mostra "3 pacientes" e lista 2 — o
    usuario deixa de confiar no aviso, que e a unica defesa contra a falha
    calada.
    """
    criar_paciente(client["db_path"], "Sem Sensor A", "alto", cama_id="Q3-L1")
    criar_paciente(client["db_path"], "Sem Sensor B", "medio", cama_id="Q3-L2")
    _com_leitura_agora(client["db_path"], "Monitorado", "Q3-L3")

    stats = (await client["client"].get("/api/stats")).json()
    monitoramento = (await client["client"].get("/api/monitoramento")).json()

    assert stats["unmonitoredPatients"] == 2
    assert monitoramento["sem_monitoramento"] == 2
    assert len(monitoramento["pacientes_sem_monitoramento"]) == 2
    assert stats["monitoringLimitMin"] == monitoramento["limite_min"]


@pytest.mark.asyncio
async def test_monitoramento_exige_autenticacao(app_isolado):
    """Nome e leito de paciente sao dados clinicos identificaveis."""
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as anon:
        resp = await anon.get("/api/monitoramento")

    assert resp.status_code == 401
