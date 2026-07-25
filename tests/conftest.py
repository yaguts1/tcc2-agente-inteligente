"""Fixtures compartilhadas da suite.

Por que existe
--------------
Nao havia conftest.py. `test_api.py`, `test_api_ingestao.py` e
`test_timeline.py` carregavam, cada um, uma copia da MESMA cadeia de
`importlib.reload()` sobre ~12 modulos, na ordem de dependencia — adicionar um
router deixava as tres copias silenciosamente desatualizadas. Outros arquivos
nem recarregavam e acabavam herdando os modulos que o arquivo anterior havia
religado a um banco temporario diferente: o teste passava isolado e falhava na
suite completa (foi o que aconteceu com test_admin_import_endpoint.py).

`APP_PREFIX`
------------
`interface/web.py` le APP_PREFIX no import e monta os routers sob ele. O
Dockerfile e o docker-compose definem `/TCC`, mas a palavra APP_PREFIX nao
aparecia uma unica vez em tests/ — a suite so exercitava rotas sem prefixo,
entao a configuracao que efetivamente vai ao ar nunca era testada. Aqui o
prefixo e fixado explicitamente, e `tests/test_app_prefix.py` cobre a montagem
sob prefixo.
"""

from __future__ import annotations

import importlib
import os
from types import SimpleNamespace

import pytest

# Fixado no IMPORT do conftest, nao numa fixture: o pytest importa este arquivo
# antes de coletar os modulos de teste, e varios deles fazem
# `from interface.web import app` no topo — a app ja nasce montada com o
# APP_PREFIX que estiver valendo. Um monkeypatch em fixture roda tarde demais e
# a app ficaria com as rotas sob /TCC enquanto os testes pedem /api/...
# (era o que quebrava a suite ao roda-la dentro do container).
# `tests/test_app_prefix.py` recarrega a app explicitamente para cobrir /TCC.
os.environ["APP_PREFIX"] = ""
os.environ["ENVIRONMENT"] = "development"

# Ordem de dependencia: api_shared primeiro (resolve DB_PATH no import),
# routers depois, e por fim api/web, que agregam tudo.
_MODULOS_EM_ORDEM = (
    "interface.api_shared",
    "interface.dependencies",
    "interface.routers.auth",
    "interface.routers.pacientes",
    "interface.routers.devices",
    "interface.services.alerts_service",
    "interface.routers.alerts",
    "interface.routers.dashboard",
    "interface.services.ingestao_service",
    "interface.routers.ingestao",
    "interface.routers.backup",
    "interface.routers.admin",
    "interface.routers.usuarios",
    "interface.endpoints_agenda",
    "interface.api",
    "interface.web",
)


def recarregar_app():
    """Recarrega a cadeia de modulos e devolve o modulo `interface.web`.

    Precisa rodar DEPOIS de definir UPP_DB_PATH/APP_PREFIX, porque varios
    modulos resolvem essas variaveis no momento do import.
    """
    modulo = None
    for nome in _MODULOS_EM_ORDEM:
        modulo = importlib.reload(importlib.import_module(nome))

    api_shared = importlib.import_module("interface.api_shared")
    api_shared._reset_auth_rate_limits()
    api_shared.reset_rate_limiter()
    importlib.import_module("interface.api").reset_processador()
    return modulo  # interface.web


@pytest.fixture(autouse=True)
def _ambiente_de_teste(monkeypatch):
    """Limpa segredos opcionais entre testes.

    Sao lidos por chamada (nao no import), entao basta o monkeypatch: um teste
    que define UPP_DEVICE_TOKEN nao pode vazar o token para o proximo.
    APP_PREFIX e ENVIRONMENT sao fixados no topo deste arquivo, porque
    precisam valer ja no import dos modulos de teste.
    """
    monkeypatch.delenv("UPP_DEVICE_TOKEN", raising=False)
    monkeypatch.delenv("UPP_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("UPP_REGISTER_TOKEN", raising=False)


@pytest.fixture
def app_isolado(tmp_path, monkeypatch):
    """App FastAPI ligado a um banco temporario proprio.

    Devolve um namespace com `.app`, `.db_path` e `.web` (o modulo recarregado,
    para quem precisa mexer em internals).
    """
    from interface.db_core import criar_esquema

    db_path = tmp_path / "dados.db"
    monkeypatch.setenv("UPP_DB_PATH", str(db_path))
    criar_esquema(str(db_path))

    web = recarregar_app()
    return SimpleNamespace(app=web.app, db_path=str(db_path), web=web)


@pytest.fixture
def cabecalho_auth():
    """Header Authorization com um JWT REAL, assinado pela mesma SECRET_KEY que
    `verify_token` usa. Nunca usar token forjado como credencial em teste."""
    from interface.auth_utils import create_access_token

    def _fabricar(username: str = "tester") -> dict:
        return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}

    return _fabricar
