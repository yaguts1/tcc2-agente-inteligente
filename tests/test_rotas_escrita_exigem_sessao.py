"""Rotas que ESCREVEM em prontuario nao podem ficar sem sessao.

As duas rotas de reconciliacao (`POST /api/device_events/reconcile` e
`.../reconcile_bed/{cama}`) foram escritas sem dependencia nenhuma, num router
onde as vizinhas de ingestao autenticam por token de dispositivo. Ficaram entre
duas convencoes e nao pegaram nenhuma das duas.

O contraste que denuncia o esquecimento: `GET /api/device_events`
(routers/devices.py:25) exige sessao para LER a mesma fila que essas duas
ESCREVEM no prontuario — grade, eventos, e os alertas calculados em cima deles.

Este arquivo existe para o esquecimento nao voltar em silencio: uma rota nova
que escreva dado clinico sem `Depends` derruba o teste.
"""

import pytest
from fastapi.testclient import TestClient

# (metodo, caminho) das rotas que alteram dado clinico e sao acionadas pela
# interface — nao pelo firmware, que tem o proprio fluxo por token.
ROTAS_DE_ESCRITA_CLINICA = [
    ("post", "/api/device_events/reconcile"),
    ("post", "/api/device_events/reconcile_bed/201-A"),
]


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


@pytest.mark.parametrize("metodo,caminho", ROTAS_DE_ESCRITA_CLINICA)
def test_sem_sessao_recusa(client, metodo, caminho):
    resposta = getattr(client, metodo)(caminho)

    assert resposta.status_code == 401, (
        f"{metodo.upper()} {caminho} aceitou requisicao anonima que escreve em prontuario"
    )


@pytest.mark.parametrize("metodo,caminho", ROTAS_DE_ESCRITA_CLINICA)
def test_com_sessao_passa(client, cabecalho_auth, metodo, caminho):
    """A recusa tem que ser por falta de sessao, nao por a rota ter sumido."""
    resposta = getattr(client, metodo)(caminho, headers=cabecalho_auth())

    assert resposta.status_code not in (401, 403), (
        f"{metodo.upper()} {caminho} recusou uma sessao valida: {resposta.text}"
    )
