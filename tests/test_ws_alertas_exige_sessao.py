"""`/api/ws/alerts` transmitia dado clinico para qualquer um.

Todas as rotas HTTP de alerta exigem sessao (`routers/alerts.py:36,70,82,91`) e
o WebSocket de INGESTAO sempre validou credencial de dispositivo. Este ficou
entre os dois e nao pegou nenhum: sem `Depends`, sem token, sem nada.

O que trafega ali e o payload de alerta — `patient_id`, `severity`, leito — e o
endpoint ainda aceita `?patient_id=PAC-0001`, entao a falta de auth nao era so
"ver o fluxo": era escolher UM paciente e acompanhar.

Nenhum teste chegava a ABRIR a conexao — os que existiam so conferiam que a
rota estava registrada, que e exatamente o tipo de cobertura que deixa um buraco
desses passar. Este arquivo abre.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

CAMINHO = "/api/ws/alerts"


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


def _token(cabecalho_auth) -> str:
    return cabecalho_auth()["Authorization"].removeprefix("Bearer ")


def test_anonimo_e_recusado(client):
    with pytest.raises(WebSocketDisconnect) as excecao, client.websocket_connect(CAMINHO):
        pass

    assert excecao.value.code == 1008, "recusa deve ser policy violation (1008)"


def test_anonimo_e_recusado_mesmo_filtrando_um_paciente(client):
    """O caso pior: escolher o paciente a espiar sem apresentar credencial."""
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"{CAMINHO}?patient_id=PAC-0001"):
        pass


def test_token_invalido_e_recusado(client):
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(
        CAMINHO, headers={"Authorization": "Bearer nao-e-um-jwt"}
    ):
        pass


def test_cookie_de_sessao_conecta(client, cabecalho_auth):
    """O caminho que a SPA usa: o navegador nao manda cabecalho no handshake de
    WebSocket, entao a credencial que precisa funcionar e o cookie `access_token`
    que login e cadastro ja gravam."""
    client.cookies.set("access_token", _token(cabecalho_auth))

    with client.websocket_connect(CAMINHO) as ws:
        ws.send_text("ping")


def test_authorization_conecta(client, cabecalho_auth):
    """Clientes nao-navegador (teste, script, painel de leito) seguem pelo header."""
    with client.websocket_connect(CAMINHO, headers=cabecalho_auth()) as ws:
        ws.send_text("ping")
