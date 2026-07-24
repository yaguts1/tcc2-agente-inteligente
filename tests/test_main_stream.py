from __future__ import annotations

import pandas as pd
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_stream_envia_eventos(tmp_path, monkeypatch):
    app = FastAPI()
    recebidos: list[dict] = []

    @app.post("/api/eventos")
    async def receber_evento(request: Request):
        payload = await request.json()
        recebidos.append(payload)
        return JSONResponse({"code": "success", "message": "ok", "ids": {"paciente_id": payload.get("paciente_id")}})

    transport = ASGITransport(app=app)

    async def fake_client(base_url: str, transport_override=None):
        return AsyncClient(base_url=base_url, transport=transport_override)

    monkeypatch.setattr(main, "_create_async_client", fake_client)

    csv_path = tmp_path / "eventos.csv"
    df = pd.DataFrame(
        {
            "device_id": ["ESP32", "ESP32"],
            "paciente_id": ["P1", "P1"],
            "cama_id": ["C01", "C01"],
            "postura": ["supino", "lateral_direito"],
            "confianca": [0.9, 0.85],
            "amostra_ms": [300000, 300000],
            "timestamp": ["2025-01-01T00:00:00", "2025-01-01T00:05:00"],
        }
    )
    df.to_csv(csv_path, index=False)

    args = main.parse_args(
        [
            "--modo",
            "stream",
            "--entrada",
            str(csv_path),
            "--formato",
            "csv",
            "--host",
            "http://testserver",
            "--endpoint",
            "/api/eventos",
            "--ritmo-ms",
            "0",
        ]
    )

    await main.run_stream(args, transport=transport)

    assert len(recebidos) == 2
    assert recebidos[0]["postura"] == "supino"
    assert recebidos[1]["postura"] == "lateral_direito"
