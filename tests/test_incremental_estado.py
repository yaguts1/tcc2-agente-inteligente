from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from configuracao import config
from servicos import metricas
from servicos.processamento_incremental import ProcessadorIncremental


def _evento(paciente_id: str, postura: str, ts: datetime, confianca: float = 0.9) -> dict:
    return {
        "device_id": "ESP32",
        "paciente_id": paciente_id,
        "cama_id": "C01",
        "postura": postura,
        "confianca": confianca,
        "amostra_ms": 300000,
        "ts_utc": ts,
    }


@pytest.fixture(autouse=True)
def _limpar_metricas():
    metricas.resetar_metricas()
    yield
    metricas.resetar_metricas()


def test_persistencia_estado_e_histerese(tmp_path: Path):
    db_path = tmp_path / "estado.db"
    proc = ProcessadorIncremental(db_path=str(db_path), estrategia="estado_em_memoria", confianca_min=0.5)

    base = datetime(2025, 1, 1, 0, 0, 0)
    alertas = []
    for i in range(30):
        alertas.extend(proc.processar_amostra(_evento("PAC-STATE", "supino", base + timedelta(minutes=5 * i))))
    assert any(alerta.get("status") == "aberto" for alerta in alertas)

    proc2 = ProcessadorIncremental(db_path=str(db_path), estrategia="estado_em_memoria", confianca_min=0.5)
    # Evento duplicado/fora de ordem deve ser ignorado
    assert proc2.processar_amostra(_evento("PAC-STATE", "supino", base + timedelta(minutes=5))) == []

    # Movimento sustentado fecha alerta (histerese)
    movimentos = []
    for i in range(config.histerese_min + 1):
        movimentos.extend(
            proc2.processar_amostra(
                _evento("PAC-STATE", "lateral_direito", base + timedelta(minutes=5 * 30 + i))
            )
        )
    assert any(alerta.get("status") == "fechado" for alerta in movimentos)

    # Após cooldown, novo alerta pode ser aberto
    inicio_novo = base + timedelta(minutes=5 * 30 + config.cooldown_min + 1)
    novos = []
    for i in range(25):
        novos.extend(proc2.processar_amostra(_evento("PAC-STATE", "supino", inicio_novo + timedelta(minutes=5 * i))))
    assert any(alerta.get("status") == "aberto" for alerta in novos)


def test_recalculo_janela_sem_regressao(tmp_path: Path):
    db_path = tmp_path / "estado.db"
    proc = ProcessadorIncremental(
        db_path=str(db_path),
        estrategia="recalcular_janela",
        janela_recalculo_min=sum(config.janela_por_perfil.values()),
        confianca_min=0.5,
    )

    base = datetime(2025, 2, 1, 0, 0, 0)
    eventos = [
        _evento("PAC-JANELA", "supino", base),
        _evento("PAC-JANELA", "supino", base + timedelta(minutes=5)),
        _evento("PAC-JANELA", "supino", base + timedelta(minutes=10)),
    ]
    assert proc.processar_lote(eventos) == []

    # Adiciona duplicado e ruido
    eventos_mistos = [
        _evento("PAC-JANELA", "supino", base + timedelta(minutes=5)),
        _evento("PAC-JANELA", "supino", base + timedelta(minutes=15), confianca=0.3),
    ]
    assert proc.processar_lote(eventos_mistos) == []

    continuacao = [
        _evento("PAC-JANELA", "supino", base + timedelta(minutes=5 * i)) for i in range(4, 22)
    ]
    alertas = proc.processar_lote(continuacao)
    assert any(alerta.get("status") == "aberto" for alerta in alertas)

    repetidos = proc.processar_lote(continuacao[-5:])
    assert repetidos == []
