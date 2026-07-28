"""Servico de processamento incremental de eventos de postura."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Mapping, Optional

import structlog

from configuracao import config
from interface.tempo import utc_naive_para_local
from nucleo.decisor import (
  EstadoDecisor,
  processar_alertas_incremental,
  processar_alertas_lote,
  reiniciar_corrida,
)
from servicos import metricas

try:  # pragma: no cover - dependencia opcional
  import redis  # type: ignore
except ImportError:
  redis = None


logger = structlog.get_logger(__name__)


class _SQLiteStateStore:
  def __init__(self, db_path: str) -> None:
    self._db_path = db_path
    self._ensure_table()

  def _ensure_table(self) -> None:
    # Garante o diretorio do banco antes de abrir. Este modulo e construido no
    # IMPORT (ingestao_service.PROCESSADOR), entao um diretorio inexistente nao
    # dava um erro de runtime: derrubava o processo inteiro no boot com
    # "unable to open database file". Acontecia ao rodar a imagem sem o volume
    # do compose montado em /data — foi assim que o smoke test do CI pegou.
    # interface/db_core.connect ja fazia isso via ensure_db_path(); aqui o
    # sqlite3.connect era chamado cru.
    pasta = os.path.dirname(os.path.abspath(self._db_path))
    if pasta:
      os.makedirs(pasta, exist_ok=True)
    with sqlite3.connect(self._db_path) as conn:
      conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estado_incremental (
          paciente_id TEXT PRIMARY KEY,
          estado_json TEXT NOT NULL,
          atualizado_em TEXT NOT NULL
        )
        """
      )

  def load(self) -> Dict[str, dict]:
    with sqlite3.connect(self._db_path) as conn:
      cursor = conn.execute("SELECT paciente_id, estado_json FROM estado_incremental")
      return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

  def save(self, paciente_id: str, state: dict) -> None:
    payload = json.dumps(state)
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with sqlite3.connect(self._db_path) as conn:
      conn.execute(
        """
        INSERT INTO estado_incremental (paciente_id, estado_json, atualizado_em)
        VALUES (?, ?, ?)
        ON CONFLICT(paciente_id) DO UPDATE SET
          estado_json = excluded.estado_json,
          atualizado_em = excluded.atualizado_em
        """,
        (paciente_id, payload, agora),
      )

  def delete(self, paciente_id: str) -> None:
    with sqlite3.connect(self._db_path) as conn:
      conn.execute("DELETE FROM estado_incremental WHERE paciente_id = ?", (paciente_id,))

  def clear(self) -> None:
    with sqlite3.connect(self._db_path) as conn:
      conn.execute("DELETE FROM estado_incremental")


class _RedisStateStore:  # pragma: no cover - dependencia nao exercitada em testes
  def __init__(self, url: str) -> None:
    if redis is None:
      raise RuntimeError("biblioteca redis nao instalada")
    self._cliente = redis.from_url(url)

  def _key(self, paciente_id: str) -> str:
    return f"estado_incremental:{paciente_id}"

  def load(self) -> Dict[str, dict]:
    estados: Dict[str, dict] = {}
    for chave in self._cliente.scan_iter(match="estado_incremental:*"):
      raw = self._cliente.get(chave)
      if raw is None:
        continue
      if isinstance(chave, bytes):
        chave = chave.decode()
      paciente_id = chave.split(":", 1)[1]
      estados[paciente_id] = json.loads(raw)
    return estados

  def save(self, paciente_id: str, state: dict) -> None:
    self._cliente.set(self._key(paciente_id), json.dumps(state))

  def delete(self, paciente_id: str) -> None:
    self._cliente.delete(self._key(paciente_id))

  def clear(self) -> None:
    chaves = list(self._cliente.scan_iter(match="estado_incremental:*"))
    if chaves:
      self._cliente.delete(*chaves)


def _coerce_datetime(valor: object) -> datetime:
  if valor is None:
    raise ValueError("timestamp ausente")
  if isinstance(valor, datetime):
    dt = valor
  else:
    texto = str(valor).strip()
    if not texto:
      raise ValueError("timestamp invalido")
    if texto.endswith("Z"):
      texto = texto[:-1] + "+00:00"
    dt = datetime.fromisoformat(texto)
  if dt.tzinfo is not None:
    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
  return dt.replace(microsecond=0)


def _estado_para_dict(estado: EstadoDecisor) -> dict:
  def _dt(valor: Optional[datetime]) -> Optional[str]:
    # `strftime("%Y-...")` depende da libc da plataforma para o ano: no Linux
    # nao faz zero-padding para anos < 1000, no Windows chega a lancar
    # ValueError. `cooldown_ate` usa datetime.min (ano 1) como sentinela de
    # "sem cooldown ativo", entao usamos isoformat() (sempre zero-padded e
    # portavel) em vez de strftime().
    return None if valor is None else valor.isoformat()

  dados = {
    "perfil": estado.perfil,
    "paciente_id": estado.paciente_id,
    "janela_min": estado.janela_min,
    "cooldown_min": estado.cooldown_min,
    "histerese_min": estado.histerese_min,
    "alerta_atual": estado.alerta_atual,
    "alerta_inicio": _dt(estado.alerta_inicio),
    "baseline_postura": estado.baseline_postura,
    "movimento_inicio": _dt(estado.movimento_inicio),
    "cooldown_ate": _dt(estado.cooldown_ate),
    "run_postura": estado.run_postura,
    "run_inicio": _dt(estado.run_inicio),
    "ultimo_timestamp": _dt(estado.ultimo_timestamp),
  }
  return dados


def _dict_para_estado(dados: Mapping[str, object]) -> EstadoDecisor:
  def _dt(valor: Optional[str]) -> Optional[datetime]:
    return None if valor is None else _coerce_datetime(valor)

  estado = EstadoDecisor(
    perfil=str(dados["perfil"]),
    paciente_id=str(dados["paciente_id"]),
    janela_min=int(dados["janela_min"]),
    cooldown_min=int(dados["cooldown_min"]),
    histerese_min=float(dados["histerese_min"]),
  )
  estado.alerta_atual = dados.get("alerta_atual") or None
  estado.alerta_inicio = _dt(dados.get("alerta_inicio"))
  estado.baseline_postura = dados.get("baseline_postura") or None
  estado.movimento_inicio = _dt(dados.get("movimento_inicio"))
  cooldown = _dt(dados.get("cooldown_ate"))
  estado.cooldown_ate = cooldown if cooldown is not None else estado.cooldown_ate
  estado.run_postura = dados.get("run_postura") or None
  estado.run_inicio = _dt(dados.get("run_inicio"))
  estado.ultimo_timestamp = _dt(dados.get("ultimo_timestamp"))
  return estado


def _resolver_perfil_default(paciente_id: str) -> str:  # pragma: no cover - substituido em integracao
  return "medio"


class ProcessadorIncremental:
  """Motor de processamento incremental com estrategias configuraveis."""

  def __init__(
    self,
    *,
    db_path: str = "dados.db",
    estrategia: str = "estado_em_memoria",
    janela_recalculo_min: int | None = None,
    confianca_min: float | None = None,
    resolver_perfil=_resolver_perfil_default,
    redis_url: str | None = None,
  ) -> None:
    if estrategia not in {"estado_em_memoria", "recalcular_janela"}:
      raise ValueError("Estrategia desconhecida.")

    if confianca_min is None:
      confianca_min = config.conf_limiar
    if janela_recalculo_min is None:
      janela_recalculo_min = max(config.janela_por_perfil.values())
    if redis_url is None:
      redis_url = config.redis_url

    self._db_path = db_path
    self._estrategia = estrategia
    self._confianca_min = confianca_min
    self._resolver_perfil = resolver_perfil

    self._estado_cache: Dict[str, EstadoDecisor] = {}
    self._ultima_ts: Dict[str, datetime] = {}
    # Quem esta dentro de uma janela de supressao agora. So serve para detectar
    # a BORDA de saida (e reiniciar a corrida uma vez), nao para decidir
    # supressao — quem decide e sempre a agenda no banco, para uma agenda criada
    # ou removida durante o turno valer na amostra seguinte.
    self._em_supressao: Dict[str, bool] = {}

    if estrategia == "estado_em_memoria":
      if redis_url:
        try:
          self._store = _RedisStateStore(redis_url)
          logger.info("estado_incremental_redis", url=redis_url)
        except RuntimeError as exc:
          logger.warning("redis_indisponivel", motivo=str(exc), fallback="sqlite")
          self._store = _SQLiteStateStore(db_path)
      else:
        self._store = _SQLiteStateStore(db_path)
        logger.info("estado_incremental_sqlite", caminho=db_path)
      self._carregar_estados_persistidos()
    else:
      self._store = None
      self._buffers: Dict[str, list] = defaultdict(list)
      self._janela_td = timedelta(minutes=janela_recalculo_min)
      self._alertas_status: Dict[str, Dict[str, str]] = defaultdict(dict)
      logger.info("processador_recalcular_janela", janela_min=janela_recalculo_min)

  # ------------------------------------------------------------------
  # Persistencia
  # ------------------------------------------------------------------
  def _carregar_estados_persistidos(self) -> None:
    registros = self._store.load()
    logger.info("estado_incremental_carregado", quantidade=len(registros))
    for paciente_id, state in registros.items():
      try:
        self._estado_cache[paciente_id] = _dict_para_estado(state)
        ultimo = self._estado_cache[paciente_id].ultimo_timestamp
        if ultimo is not None:
          self._ultima_ts[paciente_id] = ultimo
      except Exception as exc:  # pragma: no cover - apenas log
        logger.warning("estado_incremental_invalido", paciente_id=paciente_id, motivo=str(exc))
        continue

  def _persistir_estado(self, paciente_id: str) -> None:
    if self._store is None:
      return
    estado = self._estado_cache.get(paciente_id)
    if estado is None:
      self._store.delete(paciente_id)
      return
    self._store.save(paciente_id, _estado_para_dict(estado))

  # ------------------------------------------------------------------
  # Processamento principal
  # ------------------------------------------------------------------
  def processar_amostra(self, evento: Mapping[str, object]) -> list:
    return self.processar_lote([evento])

  def processar_lote(self, eventos: Iterable[Mapping[str, object]]) -> list:
    alertas_emitidos: list = []
    for evento in eventos:
      paciente_id = str(evento.get("paciente_id") or "").strip()
      postura = str(evento.get("postura") or "").strip()
      if not paciente_id or not postura:
        logger.warning("evento_sem_identificacao", evento=evento)
        continue
      confianca = float(evento.get("confianca", 1.0))
      try:
        timestamp = _coerce_datetime(evento.get("ts_utc"))
      except (TypeError, ValueError) as exc:
        logger.warning("evento_timestamp_invalido", paciente_id=paciente_id, motivo=str(exc))
        continue

      if confianca < self._confianca_min:
        logger.debug(
          "evento_confianca_baixa_ignorado",
          paciente_id=paciente_id,
          confianca=confianca,
          limiar=self._confianca_min,
        )
        continue

      ultimo = self._ultima_ts.get(paciente_id)
      if ultimo is not None and timestamp <= ultimo:
        logger.debug("evento_fora_ordem", paciente_id=paciente_id, ts=str(timestamp), ultimo=str(ultimo))
        continue

      if self._suprimir_por_agenda(paciente_id, timestamp):
        self._ultima_ts[paciente_id] = timestamp
        continue

      inicio = time.perf_counter()

      if self._estrategia == "estado_em_memoria":
        alertas = self._processar_estado_memoria(paciente_id, postura, timestamp)
      else:
        alertas = self._processar_recalculo(paciente_id, postura, timestamp)

      metricas.incrementar_evento(paciente_id)
      metricas.observar_tempo_ms((time.perf_counter() - inicio) * 1000.0)

      if alertas:
        metricas.incrementar_alertas(paciente_id, len(alertas))
        alertas_emitidos.extend(alertas)
        logger.info("alertas_gerados", paciente_id=paciente_id, quantidade=len(alertas), estrategia=self._estrategia)

      self._ultima_ts[paciente_id] = timestamp

    return alertas_emitidos

  # ------------------------------------------------------------------
  # Agenda de supressao
  # ------------------------------------------------------------------
  def _suprimir_por_agenda(self, paciente_id: str, timestamp: datetime) -> bool:
    """True quando a amostra cai numa janela em que NAO se deve alertar.

    A supressao existia so em `modulo_alerta/engine.py`, que e chamado pelo
    endpoint de simulacao e pelo CLI — nunca pelo caminho do sensor. Resultado:
    a enfermagem cadastrava "cirurgia 08:00-12:00, suprimir", via a agenda na
    tela, e o ESP32 alertava a cirurgia inteira. A funcionalidade funcionava na
    demo e nao funcionava em producao.

    A checagem e ANTES do decisor, nao depois: filtrar o alerta ja emitido
    deixaria `alerta_atual`, `baseline_postura` e `cooldown_ate` mutados por um
    alerta que ninguem viu — e um `alerta_atual` fantasma impede TODOS os
    alertas seguintes daquele paciente ate uma mudanca real de postura.

    Ao sair da janela a corrida recomeca: o periodo suprimido nao foi observado,
    entao somar as duas pontas como uma corrida continua contaria como imobilidade
    justamente o intervalo em que o paciente estava em cirurgia — sendo movido.

    Fail-safe deliberado: se a consulta a agenda quebrar, a amostra passa e o
    alerta acontece. Um alerta a mais e ruido; um alerta a menos e uma UPP que
    ninguem viu chegar. Mesma escolha (e mesmo motivo) de engine.py:80-89.
    """
    # Import tardio: `interface.dao_agenda` puxa `interface.dao`, que fecharia
    # ciclo com este modulo (interface.services.ingestao_service importa daqui).
    from interface.dao_agenda import is_timestamp_in_suppressed_period

    try:
      # O timestamp e UTC naive; as horas da agenda sao horario LOCAL do
      # hospital, que e o que a enfermagem digita.
      timestamp_local = utc_naive_para_local(timestamp)
      _, modo = is_timestamp_in_suppressed_period(
        db_path=self._db_path,
        paciente_id=paciente_id,
        timestamp=timestamp_local,
      )
    except Exception as exc:
      logger.warning("agenda_consulta_falhou", paciente_id=paciente_id, motivo=str(exc))
      return False

    if modo == "suprimir":
      if not self._em_supressao.get(paciente_id):
        self._em_supressao[paciente_id] = True
        logger.info("agenda_supressao_iniciada", paciente_id=paciente_id, ts=str(timestamp))
      return True

    if self._em_supressao.pop(paciente_id, False):
      logger.info("agenda_supressao_encerrada", paciente_id=paciente_id, ts=str(timestamp))
      estado = self._estado_cache.get(paciente_id)
      if estado is not None:
        self._estado_cache[paciente_id] = reiniciar_corrida(estado)
        self._persistir_estado(paciente_id)

    return False

  # ------------------------------------------------------------------
  def _processar_estado_memoria(self, paciente_id: str, postura: str, timestamp: datetime) -> list:
    estado = self._estado_cache.get(paciente_id)
    if estado is None:
      perfil = self._resolver_perfil(paciente_id)
      estado = EstadoDecisor.criar(perfil, paciente_id)

    novo_estado, alertas = processar_alertas_incremental(
      estado,
      {"timestamp": timestamp, "postura": postura},
    )
    self._estado_cache[paciente_id] = novo_estado
    self._persistir_estado(paciente_id)
    return alertas

  # ------------------------------------------------------------------
  def marcar_reposicionado(self, paciente_id: str) -> bool:
    """A equipe virou o paciente. O motor precisa saber.

    O botao "Reposicionar" da tela so escrevia a linha em `alertas`
    (`alterar_status_alerta`) e nada tocava o motor. Mas `nucleo/decisor.py:172`
    so abre alerta novo quando `alerta_atual is None`, e `alerta_atual` so
    limpava sozinho com postura DIFERENTE sustentada por `histerese_min`.

    O desfecho, quando o paciente nao foi virado de fato (ou o sensor nao viu):
    a linha vira 'fechado', o dashboard fica verde, `alerta_atual` continua
    preenchido — e NENHUM alerta novo nasce para aquele paciente ate uma mudanca
    real de postura. O paciente pode passar horas sobre o sacro atras de uma
    tela que afirma que esta tudo bem.

    E o inverso exato do modo de falha contra o qual
    `repositories/monitoramento.py` ja protege (silencio confundido com
    normalidade): aqui a tela nao fica calada, ela afirma bem-estar.

    Reiniciar a corrida (em vez de so limpar o alerta) e o ponto: e o que faz o
    relogio da proxima janela comecar do reposicionamento, que e quando o alivio
    de pressao de fato aconteceu.

    Devolve True se havia estado para reiniciar — o chamador usa isso para
    distinguir "motor atualizado" de "paciente que o motor nem conhecia".
    """
    estado = self._estado_cache.get(paciente_id)
    if estado is None:
      return False

    novo_estado = reiniciar_corrida(estado)
    novo_estado.alerta_atual = None
    novo_estado.alerta_inicio = None
    novo_estado.baseline_postura = None
    self._estado_cache[paciente_id] = novo_estado
    self._persistir_estado(paciente_id)
    logger.info("reposicionamento_registrado_no_motor", paciente_id=paciente_id)
    return True

  # ------------------------------------------------------------------
  def _processar_recalculo(self, paciente_id: str, postura: str, timestamp: datetime) -> list:
    buffer = self._buffers[paciente_id]
    buffer.append({"timestamp": timestamp, "postura": postura})

    limite = timestamp - self._janela_td
    buffer[:] = [evt for evt in buffer if evt["timestamp"] >= limite]

    # Ordena e remove duplicados por timestamp
    buffer.sort(key=lambda evt: evt["timestamp"])
    deduplicado = {}
    for evt in buffer:
      deduplicado[evt["timestamp"]] = evt
    buffer[:] = list(sorted(deduplicado.values(), key=lambda evt: evt["timestamp"]))

    if not buffer:
      return []

    df = [{"timestamp": evt["timestamp"].strftime("%Y-%m-%dT%H:%M:%S"), "postura": evt["postura"]} for evt in buffer]
    alertas = processar_alertas_lote(df, self._resolver_perfil(paciente_id), paciente_id)

    novos_alertas: list = []
    status_por_inicio = self._alertas_status[paciente_id]
    for alerta in alertas:
      inicio = alerta.get("inicio")
      status_alerta = alerta.get("status")
      if not inicio or not status_alerta:
        continue
      if status_por_inicio.get(inicio) != status_alerta:
        status_por_inicio[inicio] = status_alerta
        novos_alertas.append(alerta)
    return novos_alertas

  # ------------------------------------------------------------------
  def reset(self) -> None:
    self._estado_cache.clear()
    self._ultima_ts.clear()
    metricas.resetar_metricas()
    if self._estrategia == "estado_em_memoria" and self._store is not None:
      self._store.clear()
    else:
      if self._estrategia == "recalcular_janela":
        self._buffers.clear()
        self._alertas_status.clear()
    logger.info("processador_reset", estrategia=self._estrategia)
