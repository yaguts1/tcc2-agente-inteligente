"""Coletores de métricas integrados ao Prometheus."""

from __future__ import annotations

from collections import defaultdict

from prometheus_client import Counter, Histogram, Gauge

# Métricas de eventos
EVENTOS_RECEBIDOS = Counter("eventos_recebidos_total", "Total de eventos recebidos pela API.")
EVENTOS_DESCARTADOS = Counter("eventos_descartados_total", "Total de eventos descartados pela camada de filtro.")
ALERTAS_ABERTOS = Counter("alertas_abertos_total", "Total de alertas gerados pelo processador incremental.")
TEMPO_PROCESSAMENTO = Histogram(
  "tempo_processamento_ms_hist",
  "Tempo de processamento por evento (ms).",
  buckets=(5, 10, 25, 50, 100, 200, 500, 1000, float("inf")),
)

# Métricas de API HTTP
HTTP_REQUESTS_TOTAL = Counter(
  "http_requests_total",
  "Total de requisições HTTP",
  ["method", "endpoint", "status"]
)

HTTP_REQUEST_DURATION = Histogram(
  "http_request_duration_seconds",
  "Duração das requisições HTTP em segundos",
  ["method", "endpoint"],
  buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf"))
)

# Saúde do monitoramento. Esta é a métrica mais importante para alertagem de
# infraestrutura: o sistema é orientado a evento, então um sensor morto não
# gera erro nenhum — apenas para de produzir alertas, e a tela fica calma.
# Um valor > 0 aqui significa paciente em leito SEM cobertura de monitoramento.
PACIENTES_SEM_MONITORAMENTO = Gauge(
  "pacientes_sem_monitoramento",
  "Pacientes com leito atribuído sem leituras recentes (sensor/rede/ingestão)"
)

# Métricas de WebSocket
WEBSOCKET_CONNECTIONS = Gauge(
  "websocket_connections_active",
  "Número de conexões WebSocket ativas"
)

WEBSOCKET_MESSAGES_SENT = Counter(
  "websocket_messages_sent_total",
  "Total de mensagens WebSocket enviadas"
)

# Métricas de alertas
ALERTS_ACKNOWLEDGED = Counter(
  "alerts_acknowledged_total",
  "Total de alertas reconhecidos"
)

ALERTS_COMPLETED = Counter(
  "alerts_completed_total",
  "Total de alertas completados"
)

BATCH_OPERATIONS = Counter(
  "batch_operations_total",
  "Total de operações em lote",
  ["operation"]  # 'acknowledge' ou 'complete'
)

# Métricas de cache
CACHE_HITS = Counter("cache_hits_total", "Total de cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Total de cache misses")

# Métricas de rate limiting
RATE_LIMIT_EXCEEDED = Counter(
  "rate_limit_exceeded_total",
  "Total de requisições bloqueadas por rate limiting",
  ["category"]  # 'auth', 'api', 'batch'
)

_eventos_por_paciente: dict[str, int] = defaultdict(int)
_alertas_por_paciente: dict[str, int] = defaultdict(int)


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
  TEMPO_PROCESSAMENTO.observe(max(valor_ms, 0))


def registrar_request(method: str, endpoint: str, status: int, duration: float) -> None:
  """Registra uma requisição HTTP com método, endpoint, status e duração."""
  HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=str(status)).inc()
  HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)


def atualizar_websocket_connections(count: int) -> None:
  """Atualiza o número de conexões WebSocket ativas."""
  WEBSOCKET_CONNECTIONS.set(count)


def registrar_pacientes_sem_monitoramento(quantidade: int) -> None:
    """Atualiza quantos pacientes estão sem leituras recentes."""
    PACIENTES_SEM_MONITORAMENTO.set(max(0, int(quantidade)))


def registrar_websocket_message() -> None:
  """Registra uma mensagem WebSocket enviada."""
  WEBSOCKET_MESSAGES_SENT.inc()


def registrar_alert_acknowledged() -> None:
  """Registra um alerta reconhecido."""
  ALERTS_ACKNOWLEDGED.inc()


def registrar_alert_completed() -> None:
  """Registra um alerta completado."""
  ALERTS_COMPLETED.inc()


def registrar_batch_operation(operation: str, count: int = 1) -> None:
  """Registra uma operação em lote."""
  BATCH_OPERATIONS.labels(operation=operation).inc(count)


def registrar_cache_hit() -> None:
  """Registra um cache hit."""
  CACHE_HITS.inc()


def registrar_cache_miss() -> None:
  """Registra um cache miss."""
  CACHE_MISSES.inc()


def registrar_rate_limit_exceeded(category: str) -> None:
  """Registra um bloqueio por rate limiting."""
  RATE_LIMIT_EXCEEDED.labels(category=category).inc()


def obter_metricas() -> dict:
  return {
    "eventos": dict(_eventos_por_paciente),
    "alertas": dict(_alertas_por_paciente),
  }


def resetar_metricas() -> None:
  _eventos_por_paciente.clear()
  _alertas_por_paciente.clear()
