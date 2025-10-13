"""Coletores de métricas integrados ao Prometheus."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict

from prometheus_client import Counter, Histogram

EVENTOS_RECEBIDOS = Counter("eventos_recebidos_total", "Total de eventos recebidos pela API.")
EVENTOS_DESCARTADOS = Counter("eventos_descartados_total", "Total de eventos descartados pela camada de filtro.")
ALERTAS_ABERTOS = Counter("alertas_abertos_total", "Total de alertas gerados pelo processador incremental.")
TEMPO_PROCESSAMENTO = Histogram(
  "tempo_processamento_ms_hist",
  "Tempo de processamento por evento (ms).",
  buckets=(5, 10, 25, 50, 100, 200, 500, 1000, float("inf")),
)

_eventos_por_paciente: Dict[str, int] = defaultdict(int)
_alertas_por_paciente: Dict[str, int] = defaultdict(int)


def registrar_recebido() -> None:
  EVENTOS_RECEBIDOS.inc()


def registrar_descartado() -> None:
  EVENTOS_DESCARTADOS.inc()


def incrementar_evento(paciente_id: str) -> None:
  _eventos_por_paciente[paciente_id] += 1


def incrementar_alertas(paciente_id: str, quantidade: int) -> None:
  if quantidade <= 0:
    return
  _alertas_por_paciente[paciente_id] += quantidade
  ALERTAS_ABERTOS.inc(quantidade)


def observar_tempo_ms(valor_ms: float) -> None:
  TEMPO_PROCESSAMENTO.observe(max(valor_ms, 0) )


def obter_metricas() -> dict:
  return {
    "eventos": dict(_eventos_por_paciente),
    "alertas": dict(_alertas_por_paciente),
  }


def resetar_metricas() -> None:
  _eventos_por_paciente.clear()
  _alertas_por_paciente.clear()
