"""O spec OpenAPI versionado precisa descrever a API que existe.

Commitar `openapi/openapi.json` sem conferencia seria criar mais um documento
que mente: ele congela no dia em que foi gerado e passa a descrever uma API que
mudou. Em contrato de API isso custa mais caro que a ausencia do arquivo — quem
integra confia no que esta escrito e so descobre a divergencia no runtime.

Esta sessao ja corrigiu dois casos do mesmo tipo (o README do frontend
declarando quebrado o que funcionava, a docstring de `contar` prometendo
filtros que ignorava). A diferenca aqui e que a conferencia pode ser
automatica.
"""

from __future__ import annotations

import json

import pytest

from openapi.generate_openapi import CAMINHO_PADRAO, generate_openapi, serializar

COMANDO = "python -m openapi.generate_openapi"


@pytest.fixture(scope="module")
def spec_atual() -> dict:
    """Spec derivado do codigo neste momento."""
    return generate_openapi()


def test_arquivo_versionado_existe():
    assert CAMINHO_PADRAO.exists(), (
        f"{CAMINHO_PADRAO.name} nao existe. Gere com: {COMANDO}"
    )


def test_spec_versionado_esta_em_dia(spec_atual):
    """A conferencia que da sentido a commitar o arquivo."""
    em_disco = CAMINHO_PADRAO.read_text(encoding="utf-8")
    esperado = serializar(spec_atual)

    if em_disco == esperado:
        return

    # Mensagem util: dizer O QUE mudou poupa quem so quer saber se e esperado.
    rotas_disco = set(json.loads(em_disco).get("paths", {}))
    rotas_codigo = set(spec_atual.get("paths", {}))
    novas = sorted(rotas_codigo - rotas_disco)
    sumidas = sorted(rotas_disco - rotas_codigo)

    detalhe = ""
    if novas:
        detalhe += f"\n  rotas novas no codigo: {novas}"
    if sumidas:
        detalhe += f"\n  rotas que sairam do codigo: {sumidas}"
    if not detalhe:
        detalhe = "\n  as rotas sao as mesmas; mudou schema, parametro ou resposta."

    pytest.fail(
        "O spec OpenAPI versionado nao corresponde a API atual."
        f"{detalhe}\n\n  Regenere com: {COMANDO}"
    )


def test_rotas_do_app_estao_no_spec(spec_atual):
    """Guarda contra um spec que gera sem erro mas sai vazio ou truncado.

    Sem isto, um `app.openapi()` degradado passaria na comparacao (arquivo e
    codigo igualmente errados) e o teste acima nao protegeria nada.
    """
    from interface.web import app

    rotas_reais = {
        rota.path
        for rota in app.routes
        if getattr(rota, "methods", None) and rota.path.startswith("/api")
    }
    no_spec = set(spec_atual["paths"])

    faltando = sorted(rotas_reais - no_spec)
    assert not faltando, f"rotas da app ausentes do spec: {faltando}"


def test_contrato_e_publicado_sem_o_prefixo_de_implantacao(spec_atual):
    """`APP_PREFIX` e detalhe de implantacao, nao do contrato.

    Em producao a app sobe sob `/TCC`. Se o spec fosse gerado nesse ambiente,
    toda rota sairia `/TCC/api/...` e o arquivo passaria a depender de onde o
    comando foi rodado — a conferencia acusaria diferenca a cada maquina.
    """
    assert all(p.startswith("/api") or p in ("/healthz", "/metrics") for p in spec_atual["paths"]), (
        f"rotas com prefixo inesperado: {sorted(spec_atual['paths'])[:5]}"
    )


def test_schema_do_frontend_esta_declarado(spec_atual):
    """`FrontendAlert` e o formato que a SPA consome; e o motivo de o gerador
    existir em vez de se usar o `/openapi.json` cru."""
    schemas = spec_atual["components"]["schemas"]
    assert "FrontendAlert" in schemas

    resposta = spec_atual["paths"]["/api/frontend/alerts"]["get"]["responses"]["200"]
    ref = resposta["content"]["application/json"]["schema"]["items"]["$ref"]
    assert ref.endswith("/FrontendAlert")


def test_geracao_e_deterministica():
    """Se nao fosse, a conferencia falharia aleatoriamente e seria desligada —
    e o arquivo voltaria a apodrecer em silencio."""
    assert serializar(generate_openapi()) == serializar(generate_openapi())
