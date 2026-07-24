from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from servicos import metricas
from servicos.processamento_incremental import ProcessadorIncremental


def _evento(paciente_id: str, postura: str, ts: datetime, confianca: float = 0.9) -> dict:
  return {
    "paciente_id": paciente_id,
    "postura": postura,
    "ts_utc": ts,
    "confianca": confianca,
    "amostra_ms": 300000,
  }


@pytest.fixture(autouse=True)
def reset_metricas():
  metricas.resetar_metricas()
  yield
  metricas.resetar_metricas()


def test_estado_em_memoria_ignora_ruido(tmp_path: Path):
  db_path = tmp_path / "estado.db"
  processador = ProcessadorIncremental(db_path=str(db_path), estrategia="estado_em_memoria", confianca_min=0.5)

  base = datetime(2025, 1, 1, 0, 0, 0)

  # Evento com baixa confianca eh descartado
  assert processador.processar_amostra(_evento("P1", "supino", base, confianca=0.2)) == []
  # Primeiro evento valido
  assert processador.processar_amostra(_evento("P1", "supino", base)) == []
  # Evento fora de ordem deve ser ignorado
  assert processador.processar_amostra(_evento("P1", "supino", base - timedelta(minutes=5))) == []

  alertas = []
  for i in range(1, 20):
    alertas.extend(processador.processar_amostra(_evento("P1", "supino", base + timedelta(minutes=5 * i))))

  assert any(alerta.get("status") == "aberto" for alerta in alertas)

  dados_metricas = metricas.obter_metricas()
  assert dados_metricas["eventos"].get("P1") >= 20  # 1 baixa confianca + 1 valido + 1 fora ordem + 18 ciclos + ultimo
  assert dados_metricas["alertas"].get("P1", 0) >= 1

  # Persiste estado: nova instancia deve continuar sem reabrir alerta para timestamp repetido
  nova_instancia = ProcessadorIncremental(db_path=str(db_path), estrategia="estado_em_memoria", confianca_min=0.5)
  repetido = nova_instancia.processar_amostra(_evento("P1", "supino", base + timedelta(minutes=5 * 19)))
  assert repetido == []


def test_recalcular_janela_filtra_duplicados(tmp_path: Path):
  db_path = tmp_path / "estado.db"
  processador = ProcessadorIncremental(
    db_path=str(db_path),
    estrategia="recalcular_janela",
    janela_recalculo_min=180,
    confianca_min=0.5,
  )

  base = datetime(2025, 1, 2, 0, 0, 0)

  eventos_iniciais = [
    _evento("P2", "supino", base),
    _evento("P2", "supino", base + timedelta(minutes=5)),
    _evento("P2", "supino", base + timedelta(minutes=10)),
    _evento("P2", "supino", base + timedelta(minutes=5)),  # duplicado fora de ordem
    _evento("P2", "supino", base + timedelta(minutes=15), confianca=0.3),  # ruido
  ]

  assert processador.processar_lote(eventos_iniciais) == []

  eventos_continuacao = [
    _evento("P2", "supino", base + timedelta(minutes=5 * i)) for i in range(3, 20)
  ]

  alertas = processador.processar_lote(eventos_continuacao)
  assert any(alerta.get("status") == "aberto" for alerta in alertas)

  # Reprocessar mesmas amostras nao deve gerar novos alertas
  repetidos = processador.processar_lote(eventos_continuacao[-3:])
  assert repetidos == []

  dados_metricas = metricas.obter_metricas()
  assert dados_metricas["alertas"].get("P2", 0) >= 1
  assert dados_metricas["eventos"].get("P2", 0) >= len(eventos_continuacao)
