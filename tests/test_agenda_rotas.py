"""Testes de roteamento/erro dos endpoints de agenda.

Cobrem dois bugs que deixavam a API mentir sobre o que aconteceu:

1. `/agenda/check` era inalcancavel. O FastAPI casa rotas na ordem de
   declaracao e `/agenda/{agenda_id}` (int) vinha antes, entao "check" era
   parseado como agenda_id e a requisicao morria com 422.
2. `DELETE /agenda/{id}` de uma agenda inexistente devolvia 500. O
   `raise HTTPException(404)` estava dentro do `try` e era recapturado pelo
   `except Exception` generico logo abaixo.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interface.auth_utils import create_access_token
from interface.endpoints_agenda import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    # O router de agenda exige sessao autenticada (dados clinicos), entao os
    # testes precisam de um JWT REAL — assinado pela mesma SECRET_KEY que
    # verify_token usa. Nao usar token forjado.
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {create_access_token({'sub': 'tester'})}"})
    return c


def test_agenda_exige_autenticacao():
    """Sem credencial, o router de agenda responde 401."""
    app = FastAPI()
    app.include_router(router)
    sem_auth = TestClient(app)
    assert sem_auth.get("/pacientes/PAC-0001/agenda").status_code == 401


def test_check_nao_e_confundido_com_agenda_id(client):
    """`/agenda/check` nao pode ser roteado para `/agenda/{agenda_id}`."""
    with patch("interface.endpoints_agenda.is_timestamp_in_suppressed_period", return_value=(False, None)), \
         patch("interface.endpoints_agenda.dao_listar_agendas", return_value=[]):
        resp = client.get(
            "/pacientes/PAC-0001/agenda/check",
            params={"timestamp": "2026-07-25T12:00:00"},
        )

    assert resp.status_code == 200, (
        f"esperado 200, veio {resp.status_code}: {resp.text}. "
        "Se for 422 com int_parsing em agenda_id, a rota /agenda/check voltou "
        "a ser declarada DEPOIS de /agenda/{agenda_id}."
    )
    assert resp.json()["em_periodo_suprimido"] is False


def test_delete_de_agenda_inexistente_retorna_404(client):
    """Agenda inexistente e 404, nao 500."""
    with patch("interface.endpoints_agenda.dao_deletar_agenda", return_value=False):
        resp = client.delete("/pacientes/PAC-0001/agenda/999999")

    assert resp.status_code == 404, (
        f"esperado 404, veio {resp.status_code}: {resp.text}. "
        "O 404 provavelmente voltou a ser engolido pelo except Exception."
    )
    assert resp.json()["detail"]["code"] == "agenda_nao_encontrada"


def test_delete_com_falha_real_ainda_retorna_500(client):
    """Controle: uma falha genuina continua sendo 500 (nao virou 404 geral)."""
    with patch(
        "interface.endpoints_agenda.dao_deletar_agenda",
        side_effect=RuntimeError("banco indisponivel"),
    ):
        resp = client.delete("/pacientes/PAC-0001/agenda/1")

    assert resp.status_code == 500
