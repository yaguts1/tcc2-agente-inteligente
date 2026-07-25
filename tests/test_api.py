from __future__ import annotations

import importlib
import io
import json
import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.dao import criar_paciente


@pytest_asyncio.fixture()
async def api_client(app_isolado, cabecalho_auth):
    """Usa a fixture compartilhada `app_isolado` (tests/conftest.py) no lugar da
    cadeia de reload de 12 modulos que era copiada aqui, em test_timeline.py e
    em test_api_ingestao.py."""
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth()
    ) as client:
        yield {
            "client": client,
            "db_path": Path(app_isolado.db_path),
            "api_module": importlib.import_module("interface.api"),
        }


@pytest.mark.asyncio
async def test_post_eventos_persiste_grade(api_client):
    client = api_client["client"]
    db_path: Path = api_client["db_path"]

    payload = {
        "device_id": "esp32-01",
        "paciente_id": "PAC-001",
        "cama_id": "C01",
        "postura": "supino",
        "confianca": 0.92,
        "amostra_ms": 300000,
        "ts_utc": "2025-01-01T00:00:00Z",
    }

    resp = await client.post("/api/eventos", json=payload, headers={"X-Device-Id": "esp32-01"})
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["code"] == "success"
    ids = corpo["ids"]
    assert ids["processados"] == 1
    assert ids["alertas"] >= 0
    assert ids["pacientes"]["PAC-001"] == 1

    with sqlite3.connect(db_path) as conn:
        registro = conn.execute(
            "SELECT postura FROM grade WHERE paciente_id = ?",
            ("PAC-001",),
        ).fetchone()
    assert registro is not None
    assert registro[0] == "supino"


@pytest.mark.asyncio
async def test_post_eventos_valida_schema(api_client):
    client = api_client["client"]

    payload = {
        "device_id": "",
        "paciente_id": "PAC-001",
        "cama_id": "C01",
        "postura": "supino",
        "confianca": 1.5,
        "amostra_ms": -10,
        "ts_utc": "invalid",
    }

    resp = await client.post("/api/eventos", json=payload)
    assert resp.status_code == 422
    detalhe = resp.json()["detail"]
    assert detalhe["code"] == "invalid_payload"
    assert isinstance(detalhe["errors"], list)


@pytest.mark.asyncio
async def test_post_grade_processa_jsonl(api_client):
    client = api_client["client"]
    linhas = [
        {
            "device_id": "esp32-02",
            "paciente_id": "PAC-010",
            "cama_id": "C02",
            "postura": "supino",
            "confianca": 0.8,
            "amostra_ms": 120000,
            "ts_utc": "2025-01-02T00:00:00Z",
        },
        {
            "device_id": "esp32-02",
            "paciente_id": "PAC-010",
            "cama_id": "C02",
            "postura": "lateral_direito",
            "confianca": 0.75,
            "amostra_ms": 120000,
            "ts_utc": "2025-01-02T00:05:00Z",
        },
    ]
    conteudo = "\n".join(json.dumps(linha) for linha in linhas)
    arquivo = io.BytesIO(conteudo.encode("utf-8"))

    resp = await client.post(
        "/api/grade",
        files={"arquivo": ("eventos.jsonl", arquivo, "application/jsonl")},
        headers={"X-Device-Id": "esp32-02"},
    )
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["code"] == "success"
    assert corpo["ids"]["pacientes"]["PAC-010"] == 2

    with sqlite3.connect(api_client["db_path"]) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM grade WHERE paciente_id = ?",
            ("PAC-010",),
        ).fetchone()[0]
    assert total == 2


@pytest.mark.asyncio
async def test_post_grade_rejeita_json_invalido(api_client):
    client = api_client["client"]
    conteudo = "not-json\n"
    arquivo = io.BytesIO(conteudo.encode("utf-8"))

    resp = await client.post(
        "/api/grade",
        files={"arquivo": ("eventos.jsonl", arquivo, "application/jsonl")},
    )
    assert resp.status_code == 400
    detalhe = resp.json()["detail"]
    assert detalhe["code"] == "invalid_jsonl"


@pytest.mark.asyncio
async def test_get_paciente_por_cama(api_client):
    client = api_client["client"]
    db_path: Path = api_client["db_path"]

    ficha = criar_paciente(
        str(db_path),
        nome="Paciente Leito",
        perfil="alto",
        cama_id="LEITO-99",
        observacoes="Monitorado",
        rotinas=[
            {"label": "Mudanca decubito", "inicio": "06:00", "duracao_min": 30, "descricao": "Reposicionamento"},
            {"label": "Hidratacao", "inicio": "10:00", "duracao_min": 15, "ativo": False},
        ],
    )

    resp = await client.get("/api/pacientes/cama/LEITO-99")
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["paciente_id"] == ficha["paciente_id"]
    assert corpo["cama_id"] == "LEITO-99"
    assert corpo["perfil"] == "alto"
    assert corpo["nome"] == "Paciente Leito"
    assert len(corpo["rotinas"]) == 2
    assert corpo["rotinas"][0]["label"] == "Mudanca decubito"


@pytest.mark.asyncio
async def test_get_paciente_por_cama_nao_encontrado(api_client):
    client = api_client["client"]

    resp = await client.get("/api/pacientes/cama/SEM-LEITO")
    assert resp.status_code == 404
    detalhe = resp.json()["detail"]
    assert detalhe["code"] == "paciente_nao_encontrado"
