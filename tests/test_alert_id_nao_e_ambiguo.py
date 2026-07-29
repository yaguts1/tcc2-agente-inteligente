"""O identificador de alerta era desmontavel para o alerta errado.

Um alerta nao tem chave propria: a identidade e `(paciente_id, inicio)`, e a API
precisa de um id em texto para a URL. A juncao e `f"{paciente_id}__{inicio}"`.

Isso so e seguro se `paciente_id` NUNCA contiver `__` — e ele era texto livre,
sem `pattern` nem `max_length`, vindo de payload de DISPOSITIVO e indo direto
para `INSERT OR IGNORE INTO pacientes(id)`.

Duas consequencias, as duas verificadas aqui:

  * `paciente_id` com `__` faz `split("__", 1)` resolver para OUTRO alerta —
    reconhecer um alerta escreveria no registro de outro paciente;
  * `paciente_id` com `/` faz a rota nem casar, porque a barra fecha o segmento
    da URL, e o frontend nao fazia `encodeURIComponent`.

A defesa e em duas camadas de proposito: o `pattern` recusa na BORDA (onde o
dado entra) e `partir_alert_id` valida na SAIDA (para dado ja gravado antes da
validacao nao virar acesso cruzado). Uma camada so nao basta — a primeira nao
alcanca as linhas antigas, a segunda nao impede que dado ruim continue entrando.
"""

import pytest

from interface.alert_id import (
    AlertIdInvalido,
    montar_alert_id,
    paciente_id_valido,
    partir_alert_id,
)
from interface.schemas import EventPayload


# ---------------------------------------------------------------- ida e volta


def test_monta_e_parte_de_volta():
    alert_id = montar_alert_id("PAC-0001", "2026-01-01T08:00:00")

    assert partir_alert_id(alert_id) == ("PAC-0001", "2026-01-01T08:00:00")


# ---------------------------------------------------------------- ambiguidade


def test_paciente_id_com_separador_nao_resolve_para_outro_alerta():
    """O caso explorável.

    `A__2026-01-01T00:00:00` como paciente_id, somado a um inicio qualquer,
    produz uma string que `split("__", 1)` parte em
    ("A", "2026-01-01T00:00:00__X") — ou seja, resolve para o alerta de OUTRO
    paciente, num instante que nao e o pedido.
    """
    ambiguo = "A__2026-01-01T00:00:00__X"

    with pytest.raises(AlertIdInvalido):
        partir_alert_id(ambiguo)


def test_paciente_id_com_barra_e_recusado():
    with pytest.raises(AlertIdInvalido):
        partir_alert_id("a/b__2026-01-01T00:00:00")


@pytest.mark.parametrize("ruim", ["", "semseparador", "__x", "x__", "__"])
def test_formas_degeneradas_sao_recusadas(ruim):
    with pytest.raises(AlertIdInvalido):
        partir_alert_id(ruim)


# ---------------------------------------------------------------- borda


@pytest.mark.parametrize("aceito", ["PAC-0001", "P1", "CT-1", "a_b", "x.y"])
def test_identificadores_legitimos_continuam_aceitos(aceito):
    """O padrao e mais permissivo que `PAC-NNNN` de proposito: bases legadas e
    importacoes usam outros prefixos, e recusa-los rejeitaria dado clinico
    existente."""
    assert paciente_id_valido(aceito)


@pytest.mark.parametrize("recusado", ["a__b", "a/b", "_x", "x_", "a b", ""])
def test_identificadores_perigosos_sao_recusados(recusado):
    assert not paciente_id_valido(recusado)


def test_ingestao_recusa_paciente_id_com_separador():
    """A camada de borda: o dado nem entra."""
    with pytest.raises(ValueError):
        EventPayload(
            device_id="DEV-001",
            paciente_id="A__B",
            postura="supino",
            confianca=0.9,
            amostra_ms=1000,
            ts_utc="2026-01-01T08:00:00",
        )


def test_ingestao_recusa_paciente_id_com_barra():
    with pytest.raises(ValueError):
        EventPayload(
            device_id="DEV-001",
            paciente_id="a/b",
            postura="supino",
            confianca=0.9,
            amostra_ms=1000,
            ts_utc="2026-01-01T08:00:00",
        )


def test_ingestao_aceita_paciente_id_normal():
    """Ancora: sem ela, os dois testes acima passariam mesmo se o schema
    recusasse tudo."""
    evento = EventPayload(
        device_id="DEV-001",
        paciente_id="PAC-0001",
        postura="supino",
        confianca=0.9,
        amostra_ms=1000,
        ts_utc="2026-01-01T08:00:00",
    )

    assert evento.paciente_id == "PAC-0001"


def test_padrao_funciona_no_motor_de_regex_do_pydantic():
    """O padrao e compartilhado entre `re` (Python) e o pydantic-core (Rust).

    A primeira versao usava look-ahead `(?!_)`, que o motor Rust nao suporta:
    o erro nao era de validacao, era `SchemaError` no IMPORT — derrubando a
    aplicacao inteira, nao so a validacao do campo.
    """
    from interface.alert_id import PADRAO_PACIENTE_ID

    assert "(?!" not in PADRAO_PACIENTE_ID
    assert "(?=" not in PADRAO_PACIENTE_ID


# ---------------------------------------------------------------- rota


def test_rota_recusa_alert_id_malformado(app_isolado, cabecalho_auth):
    """Antes, `split` solto nunca levantava: qualquer string passava e o erro
    aparecia adiante como "alerta nao encontrado" — ou resolvia para outro."""
    from fastapi.testclient import TestClient

    client = TestClient(app_isolado.app)

    resposta = client.post(
        "/api/frontend/alerts/semseparador/acknowledge", headers=cabecalho_auth()
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["code"] == "invalid_alert_id"
