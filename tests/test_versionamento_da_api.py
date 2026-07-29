"""A API passou a atender tambem em `/api/v1`.

Nao havia versionamento nenhum. Isso importa porque ha DOIS consumidores que a
equipe nao atualiza junto com o servidor:

  * a SPA, que o usuario pode ter aberta com um bundle antigo em cache;
  * o firmware, que so muda com reflash fisico de cada ESP32 preso a um leito.

Sem um caminho versionado, qualquer mudanca de contrato quebra os dois no
instante do deploy, e nao ha como um consumidor dizer "eu falo a v1".

Os dois caminhos sao o MESMO conjunto de rotas montado duas vezes, entao sao
identicos por construcao — e e isso que estes testes travam. No dia em que
divergirem, e porque alguem decidiu versionar de verdade, e o teste vai apontar
exatamente onde.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


# Uma amostra que cobre os tres regimes de autenticacao do sistema: sessao,
# sessao de admin, e publico.
ROTAS = [
    "/api/pacientes",
    "/api/frontend/alerts",
    "/api/stats",
    "/api/monitoramento",
    "/api/unidades",
    "/api/usuarios",
]


@pytest.mark.parametrize("rota", ROTAS)
def test_os_dois_caminhos_respondem_igual(client, cabecalho_auth, rota):
    cabecalho = cabecalho_auth(role="admin")

    sem_versao = client.get(rota, headers=cabecalho)
    versionado = client.get(rota.replace("/api/", "/api/v1/", 1), headers=cabecalho)

    assert versionado.status_code == sem_versao.status_code, rota
    assert versionado.json() == sem_versao.json(), rota


@pytest.mark.parametrize("rota", ROTAS)
def test_o_caminho_versionado_exige_a_mesma_credencial(client, rota):
    """As dependencias viajam com as rotas: o alias nao pode ser uma porta sem
    autenticacao para o mesmo dado."""
    versionada = rota.replace("/api/", "/api/v1/", 1)

    assert client.get(versionada).status_code == 401, versionada


def test_versoes_e_descobrivel(client, cabecalho_auth):
    """Um mecanismo de versionamento que ninguem encontra nao serve para nada."""
    corpo = client.get("/api/versoes", headers=cabecalho_auth()).json()

    assert corpo["atual"] == "v1"
    assert "v1" in corpo["versoes"]
    assert corpo["sem_versao_atendido"] is True


def test_o_spec_nao_dobrou(app_isolado):
    """Hoje os dois caminhos sao identicos POR CONSTRUCAO — o mesmo objeto
    montado duas vezes.

    Documentar ambos dobraria o `openapi.json` e os tipos gerados a partir dele
    sem acrescentar UMA informacao, e o arquivo gerado ja tem quase 4 mil
    linhas. Quem precisa descobrir a versao usa `GET /api/versoes`.
    """
    spec = app_isolado.app.openapi()
    versionados = [c for c in spec["paths"] if c.startswith("/api/v1")]

    assert versionados == [], f"o spec passou a documentar o alias: {versionados[:3]}"
    assert "/api/versoes" in spec["paths"]


def test_ingestao_tambem_atende_versionada(client, app_isolado, monkeypatch):
    """O firmware e o consumidor que MAIS precisa fixar versao: atualiza-lo
    exige reflash fisico de cada aparelho preso a um leito."""
    monkeypatch.delenv("UPP_DEVICE_TOKEN", raising=False)
    amostra = {
        "device_id": "DEV-001",
        "paciente_id": "PAC-0001",
        "cama_id": "201-A",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 60000,
        "ts_utc": "2026-03-10T10:00:00",
    }

    resposta = client.post("/api/v1/eventos", json=amostra)

    assert resposta.status_code == 200, resposta.text
