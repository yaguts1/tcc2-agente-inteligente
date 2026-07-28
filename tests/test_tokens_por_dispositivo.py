"""Credencial por dispositivo, no lugar de um segredo unico para a frota.

`UPP_DEVICE_TOKEN` e uma variavel de ambiente com UM valor, gravado no
`config.h` de TODOS os ESP32:

  * um aparelho arrancado da parede — e sao aparelhos acessiveis, presos ao
    leito, num predio com circulacao de publico — entrega a credencial da frota
    inteira, e quem a tiver injeta postura em nome de qualquer leito;
  * revogar exigia trocar o segredo e reflashear todos os aparelhos, o que na
    pratica significa nunca revogar;
  * o token nao distingue ninguem: nao da para saber qual aparelho enviou.

O que estes testes protegem, alem do basico:

  * a MIGRACAO GRADUAL. Trocar a credencial da frota inteira num deploy so
    deixaria a ala sem monitoramento no instante da troca, entao aparelho sem
    token proprio continua aceito pelo global;
  * e o limite dela: aparelho JA MIGRADO nao aceita mais o global — senao um
    segredo global vazado seguiria falando em nome dele, e migrar nao teria
    efeito nenhum de seguranca.
"""

import pytest
from fastapi.testclient import TestClient

from interface.dependencies import credencial_de_dispositivo_ok
from interface.repositories.device_tokens import emitir, revogar, validar

DEVICE = "DEV-001"
OUTRO = "DEV-002"


@pytest.fixture
def client(app_isolado):
    return TestClient(app_isolado.app)


@pytest.fixture
def db(app_isolado):
    return app_isolado.db_path


@pytest.fixture
def sem_token_global(monkeypatch):
    monkeypatch.delenv("UPP_DEVICE_TOKEN", raising=False)


@pytest.fixture
def com_token_global(monkeypatch):
    monkeypatch.setenv("UPP_DEVICE_TOKEN", "segredo-da-frota")
    return "segredo-da-frota"


# ---------------------------------------------------------------- emissao


def test_token_emitido_e_aceito(db, sem_token_global):
    token = emitir(db, DEVICE)

    assert validar(db, DEVICE, token)


def test_token_nao_fica_em_texto_puro_no_banco(db, sem_token_global):
    """O servidor guarda so o hash. Nao ha endpoint para reler o token, e isso
    e a propriedade — nao uma limitacao."""
    from interface.db_core import connect

    token = emitir(db, DEVICE)

    with connect(db) as conn:
        guardado = conn.execute(
            "SELECT token_hash FROM device_tokens WHERE device_id = ?", (DEVICE,)
        ).fetchone()["token_hash"]

    assert token not in guardado
    assert len(guardado) == 64, "esperado SHA-256 em hex"


def test_token_de_um_aparelho_nao_vale_para_outro(db, sem_token_global):
    """O ponto inteiro: um aparelho arrancado da parede nao fala pelos outros."""
    token = emitir(db, DEVICE)
    emitir(db, OUTRO)

    assert not validar(db, OUTRO, token)


def test_emitir_de_novo_rotaciona(db, sem_token_global):
    antigo = emitir(db, DEVICE)

    novo = emitir(db, DEVICE)

    assert not validar(db, DEVICE, antigo), "o token antigo continuou valendo"
    assert validar(db, DEVICE, novo)


# ---------------------------------------------------------------- revogacao


def test_revogar_corta_o_acesso_na_hora(db, sem_token_global):
    token = emitir(db, DEVICE)

    assert revogar(db, DEVICE) is True
    assert not validar(db, DEVICE, token)


def test_revogar_preserva_o_registro(db, sem_token_global):
    """Nao apaga a linha: quem revogou e quando e justamente o que se quer
    guardar depois de um aparelho sumir."""
    from interface.db_core import connect

    emitir(db, DEVICE)
    revogar(db, DEVICE, revogado_por="chefe")

    with connect(db) as conn:
        linha = dict(
            conn.execute(
                "SELECT revogado_em, revogado_por FROM device_tokens WHERE device_id = ?",
                (DEVICE,),
            ).fetchone()
        )

    assert linha["revogado_em"] is not None
    assert linha["revogado_por"] == "chefe"


def test_revogar_duas_vezes_devolve_false(db, sem_token_global):
    emitir(db, DEVICE)
    revogar(db, DEVICE)

    assert revogar(db, DEVICE) is False


# ---------------------------------------------------------------- migracao gradual


def test_aparelho_sem_token_proprio_ainda_usa_o_global(db, com_token_global):
    """Sem isto, o deploy que introduz tokens por aparelho deixaria a ala
    inteira sem monitoramento no mesmo instante."""
    assert credencial_de_dispositivo_ok("DEV-LEGADO", com_token_global)


def test_aparelho_ja_migrado_recusa_o_token_global(db, com_token_global):
    """O limite da compatibilidade.

    Se o aparelho migrado continuasse aceitando o segredo global, um vazamento
    do global seguiria falando em nome dele — e migrar nao teria efeito nenhum
    de seguranca.
    """
    proprio = emitir(db, DEVICE)

    assert credencial_de_dispositivo_ok(DEVICE, proprio)
    assert not credencial_de_dispositivo_ok(DEVICE, com_token_global)


def test_aparelho_revogado_nao_volta_para_o_global(db, com_token_global):
    """Revogar precisa cortar o acesso, nao rebaixar para a credencial da frota.

    A primeira versao olhava so tokens ATIVOS, e por isso revogar rebaixava o
    aparelho para a credencial da frota em vez de cortar o acesso — o oposto do
    proposito da revogacao, e um jeito silencioso de um aparelho perdido
    continuar enviando. Foi este teste que pegou.
    """
    emitir(db, DEVICE)
    revogar(db, DEVICE)

    assert not credencial_de_dispositivo_ok(DEVICE, com_token_global)


def test_sem_credencial_nenhuma_configurada_a_verificacao_fica_desligada(db, sem_token_global):
    """Comportamento pre-existente, para nao derrubar bancada montada."""
    assert credencial_de_dispositivo_ok("DEV-QUALQUER", "")


# ---------------------------------------------------------------- ponta a ponta


def _amostra() -> dict:
    return {
        "device_id": DEVICE,
        "paciente_id": "PAC-0001",
        "cama_id": "201-A",
        "postura": "supino",
        "confianca": 0.9,
        "amostra_ms": 60000,
        "ts_utc": "2026-03-10T10:00:00",
    }


def test_ingestao_http_aceita_o_token_do_aparelho(client, db, com_token_global):
    token = emitir(db, DEVICE)

    resposta = client.post(
        "/api/eventos",
        json=_amostra(),
        headers={"X-Device-Id": DEVICE, "X-Device-Token": token},
    )

    assert resposta.status_code == 200, resposta.text


def test_ingestao_http_recusa_o_global_para_aparelho_migrado(client, db, com_token_global):
    emitir(db, DEVICE)

    resposta = client.post(
        "/api/eventos",
        json=_amostra(),
        headers={"X-Device-Id": DEVICE, "X-Device-Token": com_token_global},
    )

    assert resposta.status_code == 401
    assert resposta.json()["detail"]["code"] == "device_nao_autenticado"


def test_ingestao_ws_usa_a_mesma_regra(client, db, com_token_global):
    """As duas portas de ingestao nao podem discordar sobre quem pode enviar."""
    emitir(db, DEVICE)

    with client.websocket_connect("/api/ws/eventos") as ws:
        ws.send_json({"device_id": DEVICE, "cama_id": "201-A", "token": com_token_global})
        assert ws.receive_json()["error"] == "invalid_device_token"


def test_emitir_token_exige_admin(client, cabecalho_auth):
    staff = cabecalho_auth(username="enf.comum", role="staff")

    assert client.post(f"/api/devices/{DEVICE}/token", headers=staff).status_code == 403
    assert client.delete(f"/api/devices/{DEVICE}/token", headers=staff).status_code == 403
    assert client.get("/api/devices/tokens", headers=staff).status_code == 403


def test_endpoint_devolve_o_token_uma_vez_e_nunca_mais(client, cabecalho_auth, db):
    admin = cabecalho_auth(username="chefe", role="admin")

    emissao = client.post(f"/api/devices/{DEVICE}/token", headers=admin)
    assert emissao.status_code == 201, emissao.text
    token = emissao.json()["token"]

    listagem = client.get("/api/devices/tokens", headers=admin).json()
    assert listagem[0]["device_id"] == DEVICE
    assert token not in str(listagem), "o token vazou na listagem"
    assert "token_hash" not in str(listagem), "o hash nao deve sair do servidor"


def test_ingestao_aberta_so_quando_nao_ha_credencial_nenhuma(db, sem_token_global):
    """A condicao do aviso de startup.

    Alarme falso e o que ensina a equipe a ignorar o log: um deploy com todos os
    ESP32 com token proprio e sem UPP_DEVICE_TOKEN esta CORRETO, e o startup nao
    pode dizer que a ingestao esta aberta.
    """
    from interface.repositories.device_tokens import ingestao_esta_aberta

    assert ingestao_esta_aberta(db) is True, "sem nada configurado, deve avisar"

    emitir(db, DEVICE)
    assert ingestao_esta_aberta(db) is False, "frota provisionada nao esta aberta"

    revogar(db, DEVICE)
    assert ingestao_esta_aberta(db) is True, (
        "com o unico token revogado e sem global, volta a ficar aberta para os"
        " aparelhos nao provisionados"
    )


def test_ingestao_nao_esta_aberta_com_token_global(db, com_token_global):
    from interface.repositories.device_tokens import ingestao_esta_aberta

    assert ingestao_esta_aberta(db) is False
