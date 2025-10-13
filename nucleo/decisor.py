"""Nucleo do motor de decisao de alertas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import pandas as pd

from configuracao import config as app_config


def _perfil_config(perfil: str) -> Dict[str, int]:
    janelas = app_config.janela_por_perfil
    if perfil not in janelas:
        raise ValueError(f"Perfil desconhecido: {perfil}")
    janela = janelas[perfil]
    return {
        "janela_minutos": janela,
        "cooldown_minutos": app_config.cooldown_min,
        "histerese_minutos": app_config.histerese_min,
    }

NOVO_ALERTA_STATUS: Tuple[str, str] = ("aberto", "fechado")


@dataclass
class EstadoDecisor:
    """Mantem o estado incremental do motor de alertas."""

    perfil: str
    paciente_id: str
    janela_min: int
    cooldown_min: int
    histerese_min: float
    alerta_atual: Dict[str, Any] | None = None
    alerta_inicio: datetime | None = None
    baseline_postura: str | None = None
    movimento_inicio: datetime | None = None
    cooldown_ate: datetime = field(default_factory=lambda: datetime.min)
    run_postura: str | None = None
    run_inicio: datetime | None = None
    ultimo_timestamp: datetime | None = None

    @classmethod
    def criar(cls, perfil: str, paciente_id: str) -> "EstadoDecisor":
        config = _perfil_config(perfil)
        return cls(
            perfil=perfil,
            paciente_id=paciente_id,
            janela_min=int(config["janela_minutos"]),
            cooldown_min=int(config["cooldown_minutos"]),
            histerese_min=float(config["histerese_minutos"]),
        )

    def clone(self) -> "EstadoDecisor":
        alerta = None if self.alerta_atual is None else dict(self.alerta_atual)
        return EstadoDecisor(
            perfil=self.perfil,
            paciente_id=self.paciente_id,
            janela_min=self.janela_min,
            cooldown_min=self.cooldown_min,
            histerese_min=self.histerese_min,
            alerta_atual=alerta,
            alerta_inicio=self.alerta_inicio,
            baseline_postura=self.baseline_postura,
            movimento_inicio=self.movimento_inicio,
            cooldown_ate=self.cooldown_ate,
            run_postura=self.run_postura,
            run_inicio=self.run_inicio,
            ultimo_timestamp=self.ultimo_timestamp,
        )

    @property
    def janela_td(self) -> timedelta:
        return timedelta(minutes=self.janela_min)

    @property
    def cooldown_td(self) -> timedelta:
        return timedelta(minutes=self.cooldown_min)


def _to_datetime(valor: Any) -> datetime:
    if isinstance(valor, datetime):
        ts = valor
    elif isinstance(valor, pd.Timestamp):
        ts = valor.to_pydatetime()
    elif isinstance(valor, str):
        ts = datetime.fromisoformat(valor[:19])
    else:
        raise TypeError(f"Tipo de timestamp invalido: {type(valor)!r}")
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return ts.replace(microsecond=0)


def _abrir_alerta(inicio: datetime, estado: EstadoDecisor) -> Dict[str, Any]:
    return {
        "paciente_id": estado.paciente_id,
        "inicio": inicio.strftime("%Y-%m-%dT%H:%M:%S"),
        "tipo": "imobilidade",
        "perfil": estado.perfil,
        "janela_min": estado.janela_min,
        "status": NOVO_ALERTA_STATUS[0],
    }


def _fechar_alerta_inplace(alerta: Dict[str, Any], fim: datetime, inicio: datetime) -> Dict[str, Any]:
    alerta["fim"] = fim.strftime("%Y-%m-%dT%H:%M:%S")
    alerta["status"] = NOVO_ALERTA_STATUS[1]
    alerta["duracao_min"] = round((fim - inicio).total_seconds() / 60.0, 2)
    return alerta


def processar_alertas_incremental(
    estado: EstadoDecisor,
    amostra: Mapping[str, Any],
) -> Tuple[EstadoDecisor, List[Dict[str, Any]]]:
    """Atualiza o estado do motor com uma nova amostra de postura."""
    if not isinstance(estado, EstadoDecisor):
        raise TypeError("Estado deve ser uma instancia de EstadoDecisor.")
    if "timestamp" not in amostra or "postura" not in amostra:
        raise ValueError("A amostra precisa conter 'timestamp' e 'postura'.")

    novo_estado = estado.clone()
    timestamp = _to_datetime(amostra["timestamp"])
    postura = str(amostra["postura"])

    if novo_estado.ultimo_timestamp and timestamp <= novo_estado.ultimo_timestamp:
        raise ValueError("Timestamps devem estar em ordem crescente.")

    alertas_emitidos: List[Dict[str, Any]] = []

    if novo_estado.run_postura is None:
        novo_estado.run_postura = postura
        novo_estado.run_inicio = timestamp
        novo_estado.ultimo_timestamp = timestamp
        return novo_estado, alertas_emitidos

    if postura != novo_estado.run_postura:
        novo_estado.run_postura = postura
        novo_estado.run_inicio = timestamp

    if novo_estado.alerta_atual is not None and novo_estado.baseline_postura is not None:
        if postura != novo_estado.baseline_postura:
            if novo_estado.movimento_inicio is None:
                novo_estado.movimento_inicio = timestamp
            movimento_decorrido = max(
                (timestamp - novo_estado.movimento_inicio).total_seconds() / 60.0,
                0.0,
            )
        else:
            novo_estado.movimento_inicio = None
            movimento_decorrido = 0.0

        if novo_estado.movimento_inicio is not None and movimento_decorrido >= novo_estado.histerese_min:
            if novo_estado.alerta_inicio is None:
                raise RuntimeError("Estado inconsistente: alerta sem inicio registrado.")
            alerta_fechado = _fechar_alerta_inplace(
                novo_estado.alerta_atual,
                timestamp,
                novo_estado.alerta_inicio,
            )
            alertas_emitidos.append(alerta_fechado)
            novo_estado.cooldown_ate = timestamp + novo_estado.cooldown_td
            novo_estado.alerta_atual = None
            novo_estado.alerta_inicio = None
            novo_estado.baseline_postura = None
            novo_estado.movimento_inicio = None

    if novo_estado.alerta_atual is None and novo_estado.run_inicio is not None:
        detection_time = novo_estado.run_inicio + novo_estado.janela_td
        inicio_alerta = max(detection_time, novo_estado.cooldown_ate)
        if inicio_alerta <= timestamp:
            novo_estado.baseline_postura = novo_estado.run_postura
            novo_estado.alerta_inicio = inicio_alerta
            alerta_aberto = _abrir_alerta(inicio_alerta, novo_estado)
            alertas_emitidos.append(alerta_aberto)
            novo_estado.alerta_atual = alerta_aberto
            novo_estado.movimento_inicio = None

    novo_estado.ultimo_timestamp = timestamp
    return novo_estado, alertas_emitidos


def _iterar_grade(grade: Sequence[Mapping[str, Any]] | pd.DataFrame) -> Iterable[Mapping[str, Any]]:
    if isinstance(grade, pd.DataFrame):
        if not {"timestamp", "postura"}.issubset(grade.columns):
            raise ValueError("DataFrame de grade precisa conter 'timestamp' e 'postura'.")
        ordenado = grade.sort_values("timestamp").reset_index(drop=True)
        for item in ordenado.to_dict("records"):
            yield item
    else:
        for item in grade:
            if "timestamp" not in item or "postura" not in item:
                raise ValueError("Cada amostra deve conter 'timestamp' e 'postura'.")
            yield item


def processar_alertas_lote(
    grade: Sequence[Mapping[str, Any]] | pd.DataFrame,
    perfil: str,
    paciente_id: str,
) -> List[Dict[str, Any]]:
    """Processa uma grade completa de posturas e retorna alertas gerados."""
    estado = EstadoDecisor.criar(perfil, paciente_id)
    alertas_por_chave: Dict[Tuple[str, str], Dict[str, Any]] = {}
    ordem: List[Tuple[str, str]] = []
    estado_atual = estado

    for amostra in _iterar_grade(grade):
        estado_atual, novos = processar_alertas_incremental(estado_atual, amostra)
        for alerta in novos:
            chave = (str(alerta.get("paciente_id", "")), str(alerta.get("inicio", "")))
            if chave not in alertas_por_chave:
                ordem.append(chave)
            alertas_por_chave[chave] = alerta

    return [alertas_por_chave[chave] for chave in ordem]
