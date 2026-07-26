"""Respostas de erro nao podem vazar detalhes internos.

~20 endpoints devolviam `str(exc)` no corpo da resposta. Numa falha de banco
isso entrega ao navegador o texto cru do SQLite: caminho do arquivo, nomes de
tabelas e colunas, trechos de SQL. Num sistema com dados clinicos e divulgacao
de informacao, e serve de mapa para quem estiver sondando a API.

A regra: falha inesperada (500) vira mensagem generica com um `code` estavel, e
o detalhe vai para o log. Erros de validacao do proprio dominio (400/404) tem
mensagem escrita por nos e DEVEM continuar chegando ao usuario — e o que
explica o que ele fez errado.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Texto que simula uma falha real de banco, com detalhes que nao podem sair.
ERRO_INTERNO = Exception("no such column: alertas.coluna_secreta -- /data/dados.db")
VAZAMENTOS = ("coluna_secreta", "dados.db", "no such column")


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


def test_falha_de_banco_nao_expoe_detalhe(client, cabecalho_auth):
    with patch(
        "interface.routers.dashboard.selecionar_alertas_janela", side_effect=ERRO_INTERNO
    ):
        resp = client.get("/api/stats", headers=cabecalho_auth())

    assert resp.status_code == 500
    corpo = resp.text
    for fragmento in VAZAMENTOS:
        assert fragmento not in corpo, f"resposta vazou '{fragmento}': {corpo}"
    # O code precisa continuar estavel: o frontend decide o que exibir por ele.
    assert resp.json()["detail"]["code"] == "stats_error"


def test_falha_na_timeline_nao_expoe_detalhe(client, cabecalho_auth):
    with patch(
        "interface.routers.dashboard.selecionar_timeline", side_effect=ERRO_INTERNO
    ):
        resp = client.get("/api/timeline", headers=cabecalho_auth())

    assert resp.status_code == 500
    for fragmento in VAZAMENTOS:
        assert fragmento not in resp.text


def test_erro_de_validacao_ainda_explica_o_problema(client, cabecalho_auth):
    """Contrapartida: erro de validacao nosso mantem a mensagem util.

    Sanitizar tudo indistintamente deixaria o usuario sem saber o que corrigir.
    """
    resp = client.post(
        "/api/pacientes",
        json={"name": "Teste", "riskLevel": "inexistente", "room": "1", "bed": "A"},
        headers=cabecalho_auth(),
    )
    assert resp.status_code in (400, 422)
    assert "riskLevel" in resp.text, "a resposta deveria dizer QUAL campo esta errado"


def test_risklevel_invalido_nao_vira_medio_em_silencio(client, cabecalho_auth):
    """riskLevel desconhecido tem de ser rejeitado, nao rebaixado.

    O service fazia `risk_map.get(valor, "medio")`: um typo ou um valor que a
    UI nao previa ("critical", "alta") criava o paciente como risco MEDIO sem
    aviso. E parametro clinico — define a janela de reposicionamento (2h para
    alto, 3h para medio), entao o paciente era silenciosamente rebaixado.
    """
    resp = client.post(
        "/api/pacientes",
        json={"name": "Paciente Grave", "riskLevel": "critical", "room": "9", "bed": "Z"},
        headers=cabecalho_auth(),
    )
    assert resp.status_code == 422, (
        f"riskLevel invalido foi aceito ({resp.status_code}): {resp.text}"
    )

    # E o caminho valido continua funcionando, nos dois vocabularios.
    for valor in ("high", "alto"):
        ok = client.post(
            "/api/pacientes",
            json={"name": f"Paciente {valor}", "riskLevel": valor},
            headers=cabecalho_auth(),
        )
        assert ok.status_code == 201, f"{valor} deveria ser aceito: {ok.text}"
