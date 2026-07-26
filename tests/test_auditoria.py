"""Trilha de auditoria de acesso a dado clinico (LGPD).

Dado de saude e dado pessoal SENSIVEL (Art. 5o, II). O que a trilha viabiliza:

  * Art. 37 — registro das operacoes de tratamento;
  * Art. 46 — rastreabilidade do acesso;
  * Art. 48 — comunicar incidente exige saber QUAIS titulares foram expostos,
    o que so e possivel se as LEITURAS tambem forem registradas.

Por isso os testes cobrem leitura (e nao so escrita) e tentativas NEGADAS, que
sao o sinal de uso indevido.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from interface.repositories.auditoria import consultar, expurgar_anteriores_a


@pytest.fixture
def cenario(app_isolado):
    client = TestClient(app_isolado.app)

    r_admin = client.post("/api/auth/register", json={"username": "chefe", "password": "senha-inicial"})
    admin = {"Authorization": f"Bearer {r_admin.json()['token']}"}
    r_staff = client.post(
        "/api/auth/register",
        json={"username": "enfermeira", "password": "senha-inicial"},
        headers=admin,
    )
    staff = {"Authorization": f"Bearer {r_staff.json()['token']}"}
    client.cookies.clear()

    client.post(
        "/api/pacientes",
        json={"name": "Paciente Teste", "riskLevel": "high", "room": "101", "bed": "A"},
        headers=admin,
    )
    client.cookies.clear()
    return {"client": client, "db": app_isolado.db_path, "admin": admin, "staff": staff}


def test_leitura_de_paciente_e_registrada(cenario):
    """Em prontuario, QUEM CONSULTOU importa tanto quanto quem alterou."""
    c = cenario["client"]
    c.cookies.clear()
    c.get("/api/pacientes/PAC-0001", headers=cenario["staff"])

    registros = consultar(cenario["db"], paciente_id="PAC-0001")
    leituras = [r for r in registros if r["metodo"] == "GET" and r["usuario"] == "enfermeira"]
    assert leituras, f"leitura nao foi auditada: {registros}"

    r = leituras[0]
    assert r["papel"] == "staff"
    assert r["status"] == 200
    assert r["negado"] is False
    assert r["ip"]


def test_tentativa_negada_e_registrada(cenario):
    """Acesso recusado e o sinal mais util para detectar uso indevido."""
    c = cenario["client"]
    c.cookies.clear()
    c.get("/api/usuarios", headers=cenario["staff"])  # staff nao pode: 403

    negados = consultar(cenario["db"], apenas_negados=True)
    assert any(r["rota"] == "/api/usuarios" and r["usuario"] == "enfermeira" for r in negados), (
        f"tentativa negada nao foi auditada: {negados}"
    )


def test_acesso_anonimo_negado_tambem_e_registrado(cenario):
    c = cenario["client"]
    c.cookies.clear()
    c.get("/api/pacientes/PAC-0001")  # sem credencial

    negados = consultar(cenario["db"], apenas_negados=True)
    anonimos = [r for r in negados if r["usuario"] is None and r["paciente_id"] == "PAC-0001"]
    assert anonimos, "acesso anonimo negado nao foi auditado"
    assert anonimos[0]["status"] == 401


def test_consulta_por_usuario(cenario):
    """'O que o usuario Y fez?' — investigacao de uso indevido."""
    c = cenario["client"]
    c.cookies.clear()
    c.get("/api/frontend/alerts", headers=cenario["staff"])
    c.cookies.clear()
    c.get("/api/stats", headers=cenario["staff"])

    registros = consultar(cenario["db"], usuario="enfermeira")
    rotas = {r["rota"] for r in registros}
    assert "/api/frontend/alerts" in rotas
    assert "/api/stats" in rotas
    assert all(r["usuario"] == "enfermeira" for r in registros)


def test_timestamp_em_utc(cenario):
    """O banco guarda UTC naive (ver interface/tempo.py). Um ts em hora local
    tornaria a trilha inutil como prova: os horarios nao bateriam com o resto
    do sistema."""
    c = cenario["client"]
    c.cookies.clear()
    c.get("/api/stats", headers=cenario["staff"])

    registro = consultar(cenario["db"], usuario="enfermeira")[0]
    gravado = datetime.fromisoformat(registro["ts"])
    agora_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((gravado - agora_utc).total_seconds()) < 30, (
        f"ts={gravado} distante do UTC atual ({agora_utc}) — provavelmente hora local"
    )


def test_trilha_e_restrita_a_admin(cenario):
    """A propria trilha revela padroes de acesso e identificadores de paciente."""
    c = cenario["client"]
    c.cookies.clear()
    assert c.get("/api/auditoria", headers=cenario["staff"]).status_code == 403
    c.cookies.clear()
    assert c.get("/api/auditoria", headers=cenario["admin"]).status_code == 200


def test_healthz_nao_polui_a_trilha(cenario):
    """Rotas que nao tocam dado de paciente ficam de fora: inundariam a trilha
    e diluiriam o que importa."""
    c = cenario["client"]
    antes = len(consultar(cenario["db"], limit=1000))
    for _ in range(5):
        c.get("/healthz")
    assert len(consultar(cenario["db"], limit=1000)) == antes


def test_expurgo_respeita_o_corte(cenario):
    """A LGPD pede nao reter alem do necessario (Art. 15/16), mas o prazo e
    politica da instituicao — por isso o expurgo e explicito."""
    c = cenario["client"]
    c.cookies.clear()
    c.get("/api/stats", headers=cenario["staff"])
    assert consultar(cenario["db"], limit=1000)

    futuro_ms = int(datetime(2999, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    removidos = expurgar_anteriores_a(cenario["db"], futuro_ms)
    assert removidos > 0

    # Sobra exatamente o registro DO EXPURGO. Apagar o inicio da cadeia sem
    # deixar rastro seria indistinguivel de adulteracao — a remocao precisa
    # ficar documentada dentro da propria trilha que ela modificou.
    restantes = consultar(cenario["db"], limit=1000)
    assert len(restantes) == 1
    assert restantes[0]["metodo"] == "PURGE"
    assert restantes[0]["detalhe"]["removidas"] == removidos


def test_falha_ao_auditar_nao_derruba_a_requisicao(cenario, monkeypatch):
    """Auditar nao pode custar a disponibilidade do sistema clinico."""
    import interface.repositories.auditoria as mod

    monkeypatch.setattr(
        mod, "registrar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("banco fora"))
    )
    c = cenario["client"]
    c.cookies.clear()
    assert c.get("/api/stats", headers=cenario["staff"]).status_code == 200
