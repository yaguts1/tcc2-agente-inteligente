from __future__ import annotations

import importlib

import pytest

import configuracao

_ENV_KEYS = [
  "MODE",
  "REDIS_URL",
  "CONF_LIMIAR",
  "JANELA_BAIXO",
  "JANELA_MEDIO",
  "JANELA_ALTO",
  "HISTERESE_MIN",
  "COOLDOWN_MIN",
  "EVENT_JITTER_SECONDS",
]


def _limpar_env(monkeypatch):
  for chave in _ENV_KEYS:
    monkeypatch.delenv(chave, raising=False)


def test_configuracao_defaults(monkeypatch):
  _limpar_env(monkeypatch)
  monkeypatch.setattr(configuracao, "_load_env_file", dict, raising=False)
  cfg = configuracao.carregar_configuracao()
  assert cfg.modo_operacao == "batch"
  assert cfg.redis_url is None
  assert cfg.conf_limiar == pytest.approx(0.6)
  assert cfg.janela_por_perfil == {"baixo": 120, "medio": 90, "alto": 60}
  assert cfg.histerese_min == 5
  assert cfg.cooldown_min == 10
  assert cfg.event_jitter_seconds == 5


def test_configuracao_env_override(monkeypatch):
  _limpar_env(monkeypatch)
  monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
  monkeypatch.setattr(
    configuracao,
    "_load_env_file",
    lambda: {
      "MODE": "stream",
      "CONF_LIMIAR": "0.75",
      "JANELA_BAIXO": "100",
      "JANELA_MEDIO": "80",
      "JANELA_ALTO": "50",
      "HISTERESE_MIN": "7",
      "COOLDOWN_MIN": "12",
      "EVENT_JITTER_SECONDS": "3",
    },
    raising=False,
  )
  cfg = configuracao.carregar_configuracao()
  assert cfg.modo_operacao == "stream"
  assert cfg.redis_url == "redis://localhost:6379/0"
  assert cfg.conf_limiar == pytest.approx(0.75)
  assert cfg.janela_por_perfil == {"baixo": 100, "medio": 80, "alto": 50}
  assert cfg.histerese_min == 7
  assert cfg.cooldown_min == 12
  assert cfg.event_jitter_seconds == 3


def test_conf_limiar_invalid_raises(monkeypatch):
  _limpar_env(monkeypatch)
  monkeypatch.setattr(configuracao, "_load_env_file", lambda: {"CONF_LIMIAR": "abc"}, raising=False)
  with pytest.raises(ValueError):
    configuracao.carregar_configuracao()


@pytest.fixture(autouse=True)
def _restore_module():
  yield
  importlib.reload(configuracao)