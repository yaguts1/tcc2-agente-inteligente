"""Cobertura do APP_PREFIX — a configuracao que efetivamente vai ao ar.

`Dockerfile` e `docker-compose.yml` definem `APP_PREFIX=/TCC`, mas a palavra
APP_PREFIX nao aparecia uma unica vez em tests/. A suite so exercitava rotas
sem prefixo, entao um CI verde nao provava nada sobre a imagem publicada — e de
fato ~30 testes falhavam quando rodados dentro do container.

Estes testes montam a app com prefixo de verdade e verificam o contrato:
- as rotas da API respondem SOB o prefixo;
- fora do prefixo elas nao existem;
- /healthz continua na raiz, porque e o healthcheck do container
  (docker-compose.yml: curl -f http://localhost:8000/healthz).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import recarregar_app


@pytest.fixture
def app_com_prefixo(tmp_path, monkeypatch):
    from interface.db_core import criar_esquema

    db_path = tmp_path / "dados.db"
    monkeypatch.setenv("UPP_DB_PATH", str(db_path))
    monkeypatch.setenv("APP_PREFIX", "/TCC")
    criar_esquema(str(db_path))
    return recarregar_app().app


def test_healthz_fica_na_raiz(app_com_prefixo):
    """O healthcheck do container bate em /healthz sem prefixo; se sair da raiz,
    o container nunca fica healthy e o Caddy nao sobe (depends_on)."""
    with TestClient(app_com_prefixo) as client:
        assert client.get("/healthz").status_code == 200


def test_api_responde_sob_o_prefixo(app_com_prefixo, cabecalho_auth):
    with TestClient(app_com_prefixo) as client:
        resp = client.get("/TCC/api/pacientes", headers=cabecalho_auth())
        assert resp.status_code == 200, resp.text


def test_api_nao_responde_fora_do_prefixo(app_com_prefixo, cabecalho_auth):
    with TestClient(app_com_prefixo) as client:
        resp = client.get("/api/pacientes", headers=cabecalho_auth())
        assert resp.status_code == 404, (
            f"rota respondeu fora do prefixo ({resp.status_code}); o prefixo nao "
            "esta sendo aplicado de verdade"
        )


def test_sem_prefixo_a_api_fica_na_raiz(app_isolado, cabecalho_auth):
    """Contrapartida: com APP_PREFIX vazio (default do conftest) as rotas ficam
    na raiz — que e como o resto da suite as exercita."""
    with TestClient(app_isolado.app) as client:
        assert client.get("/api/pacientes", headers=cabecalho_auth()).status_code == 200
