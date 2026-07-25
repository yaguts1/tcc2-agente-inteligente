"""Deteccao de silencio: o sistema nao pode falhar calado.

O motor de alertas e orientado a evento — so processa quando dado chega. Se o
sensor morrer, o WiFi cair ou a ingestao quebrar, nao ha processamento, nao ha
alerta, e o dashboard mostrava "Nenhum alerta ativo / Todos os pacientes estao
com reposicionamento em dia".

Ou seja: silencio era indistinguivel de normalidade. Num monitoramento de
seguranca do paciente esse e o pior modo de falha possivel — pior que travar,
porque travar e visivel. Estes testes garantem que a AUSENCIA de dado produz
sinal por conta propria.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from interface.dao import inserir_grade
from interface.repositories.monitoramento import resumo, status_por_paciente
from interface.tempo import agora_utc_naive

import pandas as pd


@pytest.fixture
def leito(app_isolado):
    client = TestClient(app_isolado.app)
    r = client.post("/api/auth/register", json={"username": "chefe", "password": "senha-inicial"})
    auth = {"Authorization": f"Bearer {r.json()['token']}"}
    client.cookies.clear()

    resp = client.post(
        "/api/pacientes",
        json={"name": "Paciente Monitorado", "riskLevel": "high", "room": "101", "bed": "A"},
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    client.cookies.clear()
    return {"client": client, "db": app_isolado.db_path, "auth": auth}


def _gravar_leitura(db: str, paciente_id: str, minutos_atras: int) -> None:
    ts = agora_utc_naive() - timedelta(minutes=minutos_atras)
    inserir_grade(db, pd.DataFrame({"timestamp": [ts], "postura": ["supino"]}), paciente_id)


def test_paciente_sem_nenhuma_leitura_e_reportado(leito):
    """Nunca ter recebido dado costuma ser erro de instalacao ou de vinculo
    device-leito, e a acao corretiva e diferente de 'o sensor parou'."""
    estado = status_por_paciente(leito["db"])
    assert len(estado) == 1
    p = estado[0]
    assert p["monitorado"] is False
    assert p["nunca_recebeu_dados"] is True


def test_leitura_recente_conta_como_monitorado(leito):
    _gravar_leitura(leito["db"], "PAC-0001", minutos_atras=2)
    p = status_por_paciente(leito["db"])[0]
    assert p["monitorado"] is True
    assert p["nunca_recebeu_dados"] is False


def test_sensor_que_parou_e_detectado(leito):
    """O cenario que motivou tudo isto: houve dado, e parou."""
    _gravar_leitura(leito["db"], "PAC-0001", minutos_atras=120)
    p = status_por_paciente(leito["db"])[0]
    assert p["monitorado"] is False
    assert p["nunca_recebeu_dados"] is False
    assert p["minutos_sem_dados"] >= 119


def test_paciente_sem_leito_nao_gera_ruido(app_isolado):
    """Quem nao esta num leito nao deveria estar sendo monitorado; reporta-lo
    ensinaria a equipe a ignorar o aviso."""
    client = TestClient(app_isolado.app)
    r = client.post("/api/auth/register", json={"username": "chefe", "password": "pw"})
    auth = {"Authorization": f"Bearer {r.json()['token']}"}
    client.cookies.clear()
    client.post(
        "/api/pacientes",
        json={"name": "Sem Leito", "riskLevel": "low"},
        headers=auth,
    )
    assert status_por_paciente(app_isolado.db_path) == []


def test_stats_carrega_a_saude_do_monitoramento(leito):
    """Sem este numero no MESMO payload, a tela nao tem como distinguir
    'nenhum alerta porque esta tudo bem' de 'nenhum alerta porque parei de
    receber dados'."""
    c = leito["client"]
    c.cookies.clear()
    dados = c.get("/api/stats", headers=leito["auth"]).json()

    assert "unmonitoredPatients" in dados
    assert dados["unmonitoredPatients"] == 1  # o paciente do leito, sem leituras
    assert dados["monitoringLimitMin"] > 0

    _gravar_leitura(leito["db"], "PAC-0001", minutos_atras=1)
    c.cookies.clear()
    assert c.get("/api/stats", headers=leito["auth"]).json()["unmonitoredPatients"] == 0


def test_endpoint_de_monitoramento_detalha_por_paciente(leito):
    c = leito["client"]
    c.cookies.clear()
    dados = c.get("/api/monitoramento", headers=leito["auth"]).json()

    assert dados["total_com_leito"] == 1
    assert dados["sem_monitoramento"] == 1
    assert dados["pacientes"][0]["paciente_id"] == "PAC-0001"


def test_limite_e_configuravel(leito, monkeypatch):
    """Instalacoes com sensores de cadencia diferente precisam ajustar."""
    _gravar_leitura(leito["db"], "PAC-0001", minutos_atras=30)

    monkeypatch.setenv("MONITORAMENTO_LIMITE_MIN", "60")
    assert resumo(leito["db"])["sem_monitoramento"] == 0

    monkeypatch.setenv("MONITORAMENTO_LIMITE_MIN", "10")
    assert resumo(leito["db"])["sem_monitoramento"] == 1
