"""O que a instalação oferece a quem alcança a rede.

Três controles de exposição existiam e um detalhe de compose anulava os três: a
porta 8000 publicada em `0.0.0.0` fazia o proxy virar opcional. O `Caddyfile`
bloqueia `/metrics` com a justificativa certa — inteligência operacional sobre uma
unidade de saúde, servida sem autenticação — e quem falasse direto na porta
recebia 200.

Verificado no container em execução, antes da correção:

    http://localhost:8000/docs           -> 200
    http://localhost:8000/openapi.json   -> 200
    http://localhost:8000/TCC/metrics    -> 200
    http://localhost/TCC/metrics (Caddy) -> bloqueado

Estes testes são meta-testes de configuração, na mesma linha de
`test_deploy_imagem.py` e `test_configuracao_chega_ao_container.py`: a coisa
verificada não tem como ser exercitada localmente, então o que se afirma é o
arquivo. Frágil a refactor cosmético do YAML, e ainda assim melhor do que
descobrir em produção.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))


class TestPortasPublicadas:
    def test_app_so_escuta_em_loopback(self, compose):
        """A LAN chega pelo Caddy (80/443) ou não chega."""
        portas = compose["services"]["app"].get("ports", [])

        assert portas, "o app precisa publicar alguma porta para o Caddy alcançar"
        for porta in portas:
            assert str(porta).startswith("127.0.0.1:"), (
                f"'{porta}' publica na LAN e passa por cima do Caddy — o bloqueio de "
                "/metrics, o rate limit por X-Forwarded-For e o /docs dependem de "
                "todo tráfego externo atravessar o proxy."
            )

    def test_redis_so_escuta_em_loopback(self, compose):
        """Este Redis não tem senha. Publicado na LAN, qualquer um lê e apaga o
        buffer de amostras que ainda não foram gravadas."""
        for porta in compose["services"]["redis"].get("ports", []):
            assert str(porta).startswith("127.0.0.1:"), f"Redis sem senha exposto em '{porta}'"

    def test_so_o_caddy_publica_para_fora(self, compose):
        """Guarda contra um serviço novo repetir o erro."""
        expostos = {
            nome: definicao.get("ports", [])
            for nome, definicao in compose["services"].items()
            if any(not str(p).startswith("127.0.0.1:") for p in definicao.get("ports", []))
        }

        assert set(expostos) <= {"caddy"}, (
            f"serviços publicando na LAN além do Caddy: {expostos}"
        )


class TestDocumentacaoInterativa:
    """`/docs` e `/openapi.json` moram na RAIZ, fora do `APP_PREFIX`.

    Isso as coloca fora do alcance de qualquer regra do proxy — o Caddy nem sabe
    que existem sob esse caminho. Não vazam dado clínico; vazam o mapa completo
    para chegar nele, incluindo as rotas administrativas.
    """

    def _app_com_ambiente(self, monkeypatch, ambiente: str):
        monkeypatch.setenv("ENVIRONMENT", ambiente)
        if ambiente == "production":
            # `em_producao()` só é verdade com os segredos definidos; sem isto o
            # import falha antes de chegar ao que se quer testar.
            monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
        for modulo in ("interface.auth_utils", "interface.web"):
            importlib.reload(importlib.import_module(modulo))
        return importlib.import_module("interface.web").app

    def test_desligada_em_producao(self, monkeypatch):
        app = self._app_com_ambiente(monkeypatch, "production")

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    def test_ligada_em_desenvolvimento(self, monkeypatch):
        """Em bancada ela serve para alguma coisa, e o risco é outro."""
        app = self._app_com_ambiente(monkeypatch, "development")

        assert app.docs_url == "/docs"
        assert app.openapi_url == "/openapi.json"


class TestOGuiaNaoEnsinaOCaminhoErrado:
    def test_guia_de_deploy_nao_manda_curl_em_docs(self):
        """O guia usava `curl .../docs` como passo de verificação. Com a doc
        desligada em produção isso passa a responder 404, e um passo de checklist
        que falha sempre é um passo que se aprende a ignorar."""
        guia = (RAIZ / "GUIA_BUILD_DEPLOYMENT.md").read_text(encoding="utf-8")

        assert not re.search(r"curl[^\n]*/docs\b", guia), (
            "GUIA_BUILD_DEPLOYMENT.md ainda verifica o deploy por /docs, que agora "
            "é 404 em produção. Use /healthz."
        )
