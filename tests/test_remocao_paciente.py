"""Remocao de paciente: a rota que a tela chamava e nao existia.

O botao "Excluir" da tela de Pacientes chamava `DELETE /api/pacientes/{id}`
desde sempre; a rota nunca foi declarada, entao o FastAPI respondia 405 e o
paciente continuava na lista. `PatientRepository.delete` e `dao.remover_paciente`
ja estavam escritos, sem nenhum chamador em producao.
"""

from __future__ import annotations

import sqlite3

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.dao import criar_paciente, inserir_alertas, inserir_timeline_event


@pytest_asyncio.fixture()
async def client_admin(app_isolado, cabecalho_auth):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth(username="admin1", role="admin")
    ) as client:
        yield {"client": client, "db_path": app_isolado.db_path}


def _paciente_com_historico(db_path: str) -> str:
    ficha = criar_paciente(db_path, "Paciente Removivel", "alto", cama_id="Q1-L1")
    pid = ficha["paciente_id"]
    inserir_alertas(
        db_path,
        [
            {
                "paciente_id": pid,
                "inicio": "2026-05-01T10:00:00",
                "fim": None,
                "tipo": "imobilidade",
                "perfil": "alto",
                "janela_min": 120,
                "status": "aberto",
                "duracao_min": 130,
            }
        ],
    )
    inserir_timeline_event(db_path, pid, "2026-05-01T10:00:00", 1777629600000, "alert_open", "Aberto")
    return pid


@pytest.mark.asyncio
async def test_remover_paciente_responde_200_e_some_da_lista(client_admin):
    """A rota existe: antes disto o 405 fazia o botao falhar sempre."""
    client = client_admin["client"]
    pid = _paciente_com_historico(client_admin["db_path"])

    resp = await client.delete(f"/api/pacientes/{pid}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    listagem = await client.get("/api/pacientes")
    assert all(p["id"] != pid for p in listagem.json())


@pytest.mark.asyncio
async def test_remocao_leva_o_alerta_junto(client_admin):
    """Alerta orfao voltava ao dashboard rotulado com o ID cru do paciente.

    A cascata nao incluia `alertas`: a ficha sumia e a linha em `alertas`
    ficava. `listar_alertas_frontend` resolve nome e leito pela ficha e cai
    para o proprio `paciente_id` quando ela nao existe — entao o alerta
    reaparecia como "PAC-000X", sem quarto, de alguem que nao existe mais.
    """
    client = client_admin["client"]
    db_path = client_admin["db_path"]
    pid = _paciente_com_historico(db_path)

    antes = await client.get("/api/frontend/alerts?horas=100000")
    assert any(a["id"].startswith(pid) for a in antes.json())

    resp = await client.delete(f"/api/pacientes/{pid}")
    assert resp.status_code == 200

    with sqlite3.connect(db_path) as conn:
        restantes = conn.execute(
            "SELECT COUNT(*) FROM alertas WHERE paciente_id = ?", (pid,)
        ).fetchone()[0]
    assert restantes == 0

    depois = await client.get("/api/frontend/alerts?horas=100000")
    assert all(not a["id"].startswith(pid) for a in depois.json()), (
        "alerta do paciente removido voltou a listagem"
    )


@pytest.mark.asyncio
async def test_resposta_diz_o_tamanho_do_que_foi_apagado(client_admin):
    """Operacao irreversivel tem que reportar o proprio alcance.

    A contagem devolvida e comparada com o que havia no banco ANTES: e o que
    garante que o numero na tela corresponde ao estrago, e nao a um contador
    qualquer.
    """
    client = client_admin["client"]
    db_path = client_admin["db_path"]
    pid = _paciente_com_historico(db_path)

    with sqlite3.connect(db_path) as conn:
        antes = {
            tabela: conn.execute(
                f"SELECT COUNT(*) FROM {tabela} WHERE paciente_id = ?", (pid,)
            ).fetchone()[0]
            for tabela in ("alertas", "timeline_events", "paciente_fichas")
        }
    assert antes["alertas"] == 1 and antes["timeline_events"] >= 1

    resp = await client.delete(f"/api/pacientes/{pid}")

    removidos = resp.json()["removidos"]
    for tabela, esperado in antes.items():
        assert removidos[tabela] == esperado, f"{tabela}: reportou {removidos[tabela]}, apagou {esperado}"


@pytest.mark.asyncio
async def test_remover_paciente_inexistente_e_404(client_admin):
    """404, e nao 200: o cliente precisa distinguir "apaguei" de "nao achei"."""
    client = client_admin["client"]

    resp = await client.delete("/api/pacientes/PAC-9999")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "paciente_nao_encontrado"


@pytest.mark.asyncio
async def test_remocao_exige_papel_admin(app_isolado, cabecalho_auth):
    """Mesma regra de /simular: acao irreversivel sobre historico clinico."""
    db_path = app_isolado.db_path
    pid = _paciente_com_historico(db_path)

    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", headers=cabecalho_auth(username="enfermeiro1", role="enfermeiro")
    ) as comum:
        resp = await comum.delete(f"/api/pacientes/{pid}")

    assert resp.status_code == 403
    with sqlite3.connect(db_path) as conn:
        ainda_existe = conn.execute(
            "SELECT COUNT(*) FROM paciente_fichas WHERE paciente_id = ?", (pid,)
        ).fetchone()[0]
    assert ainda_existe == 1


@pytest.mark.asyncio
async def test_remocao_exige_autenticacao(app_isolado):
    """Sem credencial nao se apaga prontuario."""
    pid = _paciente_com_historico(app_isolado.db_path)

    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as anon:
        resp = await anon.delete(f"/api/pacientes/{pid}")

    assert resp.status_code == 401
