"""Leitura centralizada de configuracoes do projeto."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from logging_setup import configure_logging

# Configura o logging no import deste modulo, que e carregado cedo por todo o
# app. Os imports acima sao da stdlib e nao emitem log, entao nao precisam vir
# depois desta chamada — estavam abaixo dela sem motivo.
configure_logging()

_ENV_ROOT = Path(__file__).resolve().parent


def _load_env_file() -> Dict[str, str]:
  caminho = _ENV_ROOT / ".env"
  if not caminho.exists():
    return {}
  dados: Dict[str, str] = {}
  for linha in caminho.read_text(encoding="utf-8").splitlines():
    linha = linha.strip()
    if not linha or linha.startswith("#") or "=" not in linha:
      continue
    chave, valor = linha.split("=", 1)
    dados[chave.strip()] = valor.strip()
  return dados


def _get_env(chave: str, default: str | None = None, origem: Dict[str, str] | None = None) -> str | None:
  if origem is None:
    origem = {}
  valor = os.getenv(chave)
  if valor is not None:
    return valor
  return origem.get(chave, default)


def _parse_int(nome: str, valor: str | None, minimo: int = 1, fallback: int = 1) -> int:
  try:
    numero = int(valor) if valor is not None else fallback
  except ValueError as exc:
    raise ValueError(f"{nome} deve ser inteiro") from exc
  if numero < minimo:
    raise ValueError(f"{nome} deve ser >= {minimo}")
  return numero


def _parse_float(nome: str, valor: str | None, minimo: float = 0.0, maximo: float = 1.0, fallback: float = 0.0) -> float:
  try:
    numero = float(valor) if valor is not None else fallback
  except ValueError as exc:
    raise ValueError(f"{nome} deve ser numerico") from exc
  if numero < minimo or numero > maximo:
    raise ValueError(f"{nome} deve estar entre {minimo} e {maximo}")
  return numero


@dataclass(frozen=True)
class Configuracao:
  modo_operacao: str
  redis_url: str | None
  conf_limiar: float
  janela_baixo_min: int
  janela_medio_min: int
  janela_alto_min: int
  histerese_min: int
  cooldown_min: int
  event_jitter_seconds: int
  db_path: str

  @property
  def janela_por_perfil(self) -> Dict[str, int]:
    return {
      "baixo": self.janela_baixo_min,
      "medio": self.janela_medio_min,
      "alto": self.janela_alto_min,
    }


def carregar_configuracao() -> Configuracao:
  origem_env = _load_env_file()

  modo = _get_env("MODE", "batch", origem_env)
  if modo is None or modo.lower() not in {"batch", "stream"}:
    modo = "batch"
  else:
    modo = modo.lower()

  redis_url = _get_env("REDIS_URL", None, origem_env)
  
  db_path = _get_env("UPP_DB_PATH", "dados.db", origem_env)

  conf_limiar = _parse_float("CONF_LIMIAR", _get_env("CONF_LIMIAR", None, origem_env), minimo=0.0, maximo=1.0, fallback=0.6)

  janela_baixo = _parse_int("JANELA_BAIXO", _get_env("JANELA_BAIXO", None, origem_env), minimo=1, fallback=120)
  janela_medio = _parse_int("JANELA_MEDIO", _get_env("JANELA_MEDIO", None, origem_env), minimo=1, fallback=90)
  janela_alto = _parse_int("JANELA_ALTO", _get_env("JANELA_ALTO", None, origem_env), minimo=1, fallback=60)

  histerese = _parse_int("HISTERESE_MIN", _get_env("HISTERESE_MIN", None, origem_env), minimo=1, fallback=5)
  cooldown = _parse_int("COOLDOWN_MIN", _get_env("COOLDOWN_MIN", None, origem_env), minimo=1, fallback=10)

  jitter = _parse_int("EVENT_JITTER_SECONDS", _get_env("EVENT_JITTER_SECONDS", None, origem_env), minimo=0, fallback=5)

  return Configuracao(
    modo_operacao=modo,
    redis_url=redis_url,
    conf_limiar=conf_limiar,
    janela_baixo_min=janela_baixo,
    janela_medio_min=janela_medio,
    janela_alto_min=janela_alto,
    histerese_min=histerese,
    cooldown_min=cooldown,
    event_jitter_seconds=jitter,
    db_path=db_path,
  )


config = carregar_configuracao()
