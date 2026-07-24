from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import main


class DummyResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


class DummyClient:
    async def post(self, endpoint: str, json: dict) -> DummyResponse:
        return DummyResponse(200)

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_stream_envia_10k_eventos(tmp_path, monkeypatch):
    jsonl_path = tmp_path / "bulk.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as arquivo:
        for idx in range(10_000):
            arquivo.write(
                '{"device_id":"ESP","paciente_id":"P%02d","cama_id":"C01","postura":"supino",'
                '"confianca":0.9,"amostra_ms":300000,"ts_utc":"2025-01-01T00:%02d:00"}\n'
                % (idx % 5, idx % 60)
            )

    monkeypatch.setattr(main, "_create_async_client", lambda base_url, transport=None: DummyClient())

    async def fake_enviar(client, endpoint, evento, retries, backoff_ms):
        await asyncio.sleep(0)
        return True

    monkeypatch.setattr(main, "_enviar_evento", fake_enviar)

    args = main.parse_args(
        [
            "--modo",
            "stream",
            "--entrada",
            str(jsonl_path),
            "--formato",
            "jsonl",
            "--host",
            "http://example",
            "--ritmo-ms",
            "0",
        ]
    )

    resumo = await main.run_stream(args)
    assert resumo["processados"] == 10_000
    assert resumo["perdas"] == 0
    assert resumo["lat_p95"] < 200
