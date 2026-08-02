from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest_asyncio.fixture()
async def api_client(app_isolado):
    """Usa a fixture compartilhada `app_isolado` (tests/conftest.py).

    A ingestao nao usa JWT de usuario: autentica por token de dispositivo, que
    o conftest deixa desconfigurado — nesse modo a verificacao fica desligada,
    entao nao ha header a enviar aqui.
    """
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "client": client,
            "db_path": Path(app_isolado.db_path),
            "api": importlib.import_module("interface.api"),
        }


@pytest.mark.asyncio
async def test_evento_duplicado_descartado(api_client):
    client = api_client["client"]
    payload = {
        "device_id": "ESP1",
        "paciente_id": "PAC-001",
        "cama_id": "C01",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 300000,
        "ts_utc": "2025-01-01T00:00:00Z",
    }

    resp1 = await client.post("/api/eventos", json=payload)
    assert resp1.status_code == 200
    resp2 = await client.post("/api/eventos", json=payload)
    assert resp2.status_code == 200
    corpo2 = resp2.json()
    assert corpo2["code"] == "accepted"
    assert corpo2["ids"]["processados"] == 0


@pytest.mark.asyncio
async def test_evento_fora_de_ordem_sem_alerta(api_client):
    client = api_client["client"]
    base = {
        "device_id": "ESP1",
        "paciente_id": "PAC-002",
        "cama_id": "C02",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 300000,
    }
    resp1 = await client.post("/api/eventos", json={**base, "ts_utc": "2025-01-01T00:10:00Z"})
    assert resp1.status_code == 200
    resp2 = await client.post("/api/eventos", json={**base, "ts_utc": "2025-01-01T00:05:00Z"})
    assert resp2.status_code == 200
    corpo2 = resp2.json()
    assert corpo2["ids"]["alertas"] == 0


@pytest.mark.asyncio
async def test_evento_ruido_descartado(api_client):
    client = api_client["client"]
    payload = {
        "device_id": "ESP1",
        "paciente_id": "PAC-003",
        "cama_id": "C03",
        "postura": "supino",
        "confianca": 0.2,
        "amostra_ms": 300000,
        "ts_utc": "2025-01-01T00:00:00Z",
    }
    resp = await client.post("/api/eventos", json=payload)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["code"] == "accepted"
    assert corpo["ids"]["processados"] == 0


@pytest.mark.asyncio
async def test_grade_jsonl_processa_somente_validos(api_client):
    client = api_client["client"]
    arquivo = FIXTURES_DIR / "eventos_validos.jsonl"
    files = {"arquivo": (arquivo.name, arquivo.read_bytes(), "application/jsonl")}

    resp = await client.post("/api/grade", files=files)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["code"] == "success"
    assert corpo["ids"]["processados"] == 3

    with sqlite3.connect(api_client["db_path"]) as conn:
        total = conn.execute("SELECT COUNT(*) FROM grade").fetchone()[0]
    assert total == 3


@pytest.mark.asyncio
async def test_grade_jsonl_ruido(api_client):
    client = api_client["client"]
    arquivo = FIXTURES_DIR / "ruidos.jsonl"
    files = {"arquivo": (arquivo.name, arquivo.read_bytes(), "application/jsonl")}

    resp = await client.post("/api/grade", files=files)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["ids"]["processados"] == 0


class TestEventoOrfaoEPersistido:
    """Dispositivo que envia ANTES de a cama ter paciente.

    É o estado normal de uma instalação nova, de uma troca de leito, ou do
    ESP32 energizado cedo demais na bancada. O evento não tem dono ainda, então
    é guardado cru em `device_events` para a reconciliação resolver depois.

    O defeito: `receber_evento` monta o dicionário com `model_dump(mode="python")`
    — `ts_utc` continua sendo um `datetime` — e `inserir_device_event` fazia
    `json.dumps` nele, que levanta `TypeError`. O caminho falhava SEMPRE, e o
    comentário logo acima dele explica o custo: "Este é o ÚNICO lugar onde a
    amostra é guardada. Se falhar, o dado do sensor está perdido".

    A rota respondia 503, que o firmware classifica como TRANSIENTE, então o
    aparelho reenviava para sempre sem nunca conseguir gravar. Silencioso do
    lado de quem olha o dashboard: nenhum alerta, nenhum paciente, nenhuma
    pista.

    Só aparecia pela rota HTTP com um `EventPayload` de verdade — os testes que
    chamavam `inserir_device_event` direto passavam um dicionário de strings, e
    strings o `json` serializa sem reclamar.
    """

    @pytest.mark.asyncio
    async def test_evento_sem_paciente_e_aceito_e_guardado(self, api_client):
        resp = await api_client["client"].post(
            "/api/eventos",
            json={
                "device_id": "ESP-ORFAO",
                "cama_id": "C-SEM-DONO",
                "postura": "supino",
                "confianca": 0.9,
                "amostra_ms": 300000,
                "ts_utc": "2026-08-02T12:00:00Z",
            },
        )

        assert resp.status_code == 200, (
            f"o evento órfão precisa ser aceito, e veio {resp.status_code}: {resp.text}"
        )
        assert resp.json()["code"] == "accepted"

        with sqlite3.connect(api_client["db_path"]) as conn:
            linhas = conn.execute(
                "SELECT payload FROM device_events WHERE device_id = ?", ("ESP-ORFAO",)
            ).fetchall()

        assert len(linhas) == 1, "a amostra sem dono precisa estar guardada, não perdida"

        # E o que ficou guardado tem que ser relegível: é isso que a
        # reconciliação lê depois (`json.loads` em `listar_device_events`).
        import json as _json

        guardado = _json.loads(linhas[0][0])
        assert guardado["device_id"] == "ESP-ORFAO"
        assert guardado["ts_utc"].startswith("2026-08-02T12:00:00"), (
            "o timestamp precisa sobreviver em ISO-8601, não como repr de datetime"
        )
