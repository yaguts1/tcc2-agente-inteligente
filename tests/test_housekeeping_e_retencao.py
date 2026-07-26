"""Limpezas periodicas e retencao da trilha de auditoria.

`limpar_tokens_expirados` e `expurgar_anteriores_a` existiam prontas e sem
nenhum chamador em producao — so os testes as exercitavam. A primeira e
higiene pura; a segunda apaga trilha de auditoria, e por isso a docstring dela
diz que deve ser "uma operacao explicita, e nao um expurgo automatico com
prazo arbitrario". Estes testes fixam essa distincao.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta, timezone
from unittest import mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from interface.lifespan_tasks import ciclo_housekeeping, retencao_auditoria_dias
from interface.repositories.auditoria import contar, expurgar_anteriores_a, registrar
from interface.tempo import agora_utc_naive


@pytest_asyncio.fixture()
async def client_admin(app_isolado, cabecalho_auth):
    transport = ASGITransport(app=app_isolado.app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=cabecalho_auth(username="admin1", role="admin"),
    ) as c:
        yield {"client": c, "db_path": app_isolado.db_path}


def _ms(dt) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _entrada(db_path: str, dias_atras: int, usuario: str = "alguem") -> None:
    """Grava uma entrada na trilha com data no passado.

    Passa pelo `registrar` de verdade (com o relogio deslocado) em vez de um
    INSERT direto: a trilha e encadeada por hash, e uma linha inserida por fora
    quebraria a cadeia — o teste passaria a exercitar um estado que o codigo
    nunca produz.
    """
    quando = agora_utc_naive() - timedelta(days=dias_atras)
    with mock.patch(
        "interface.repositories.auditoria.agora_utc_naive", return_value=quando
    ):
        registrar(
            db_path,
            metodo="GET",
            rota="/api/pacientes/PAC-0001",
            status=200,
            usuario=usuario,
            papel="enfermeiro",
            paciente_id="PAC-0001",
        )


class TestRetencaoConfigurada:
    """Sem politica declarada, nada e apagado — o lado seguro do erro."""

    def test_sem_variavel_nao_expurga(self, monkeypatch):
        monkeypatch.delenv("AUDITORIA_RETENCAO_DIAS", raising=False)
        assert retencao_auditoria_dias() is None

    def test_valor_ilegivel_nao_expurga(self, monkeypatch):
        # Diante de configuracao que nao se entende, nao apagar.
        monkeypatch.setenv("AUDITORIA_RETENCAO_DIAS", "seis meses")
        assert retencao_auditoria_dias() is None

    def test_valor_nao_positivo_nao_expurga(self, monkeypatch):
        # `0` seria "apagar tudo" — jamais por acidente de configuracao.
        monkeypatch.setenv("AUDITORIA_RETENCAO_DIAS", "0")
        assert retencao_auditoria_dias() is None
        monkeypatch.setenv("AUDITORIA_RETENCAO_DIAS", "-30")
        assert retencao_auditoria_dias() is None

    def test_valor_valido_e_respeitado(self, monkeypatch):
        monkeypatch.setenv("AUDITORIA_RETENCAO_DIAS", "365")
        assert retencao_auditoria_dias() == 365


class TestExpurgo:
    def test_remove_apenas_o_que_passou_do_prazo(self, app_isolado):
        db_path = app_isolado.db_path
        _entrada(db_path, dias_atras=400)
        _entrada(db_path, dias_atras=10)

        corte = _ms(agora_utc_naive() - timedelta(days=365))
        removidas = expurgar_anteriores_a(db_path, corte)

        assert removidas == 1
        with sqlite3.connect(db_path) as conn:
            restantes = conn.execute(
                "SELECT COUNT(*) FROM auditoria WHERE rota = '/api/pacientes/PAC-0001'"
            ).fetchone()[0]
        assert restantes == 1

    def test_o_expurgo_se_registra_na_propria_trilha(self, app_isolado):
        """Apagar o inicio da cadeia e indistinguivel de adulteracao.

        Se a remocao nao ficar documentada dentro do que ela modificou, quem
        verificar a integridade depois nao consegue diferenciar expurgo
        legitimo de alguem apagando rastro.
        """
        db_path = app_isolado.db_path
        _entrada(db_path, dias_atras=400)

        expurgar_anteriores_a(db_path, _ms(agora_utc_naive() - timedelta(days=365)))

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            purges = conn.execute(
                "SELECT * FROM auditoria WHERE metodo = 'PURGE'"
            ).fetchall()
        assert len(purges) == 1


@pytest.mark.asyncio
class TestCicloDeHousekeeping:
    """O ciclo agendado: sempre limpa token, so expurga trilha se configurado."""

    async def test_sem_retencao_nao_toca_na_trilha(self, app_isolado, monkeypatch):
        monkeypatch.delenv("AUDITORIA_RETENCAO_DIAS", raising=False)
        db_path = app_isolado.db_path
        _entrada(db_path, dias_atras=5000)

        resultado = await ciclo_housekeeping(db_path)

        assert resultado["auditoria"] == 0
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 1

    async def test_com_retencao_expurga_o_que_passou(self, app_isolado, monkeypatch):
        monkeypatch.setenv("AUDITORIA_RETENCAO_DIAS", "365")
        db_path = app_isolado.db_path
        _entrada(db_path, dias_atras=400)
        _entrada(db_path, dias_atras=10)

        resultado = await ciclo_housekeeping(db_path)

        assert resultado["auditoria"] == 1

    async def test_limpa_token_revogado_ja_expirado(self, app_isolado):
        """Depois de expirado o token seria recusado de qualquer forma; a linha
        so fazia a tabela crescer sem limite."""
        db_path = app_isolado.db_path
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO tokens_revogados (jti, expira_em) VALUES (?, ?)",
                ("jti-velho", "2020-01-01T00:00:00Z"),
            )
            conn.commit()

        resultado = await ciclo_housekeeping(db_path)

        assert resultado["tokens"] == 1

    async def test_falha_numa_limpeza_nao_impede_a_outra(self, app_isolado, monkeypatch):
        """As duas rotinas sao independentes: uma quebrada nao pode calar a outra."""
        monkeypatch.setenv("AUDITORIA_RETENCAO_DIAS", "365")
        db_path = app_isolado.db_path
        _entrada(db_path, dias_atras=400)

        with mock.patch(
            "interface.repositories.sessoes.limpar_tokens_expirados",
            side_effect=RuntimeError("banco travado"),
        ):
            resultado = await ciclo_housekeeping(db_path)

        assert resultado["tokens"] == 0
        assert resultado["auditoria"] == 1


class TestContarRespeitaFiltros:
    """`contar` recebia `**filtros` e ignorava TODOS.

    Contava a tabela inteira enquanto a docstring prometia o total dos que
    casam com os filtros. Como nada em producao a chamava, o defeito nunca
    apareceu — e apareceria agora, ao paginar a consulta filtrada, na forma de
    um total maior que o real.
    """

    def test_filtro_por_usuario(self, app_isolado):
        db_path = app_isolado.db_path
        _entrada(db_path, dias_atras=1, usuario="ana")
        _entrada(db_path, dias_atras=2, usuario="bruno")
        _entrada(db_path, dias_atras=3, usuario="bruno")

        assert contar(db_path, usuario="bruno") == 2
        assert contar(db_path, usuario="ana") == 1

    def test_filtro_por_intervalo(self, app_isolado):
        db_path = app_isolado.db_path
        _entrada(db_path, dias_atras=1)
        _entrada(db_path, dias_atras=100)

        desde = _ms(agora_utc_naive() - timedelta(days=30))
        assert contar(db_path, desde_ms=desde) == 1


@pytest.mark.asyncio
class TestEndpointDeExpurgo:
    """`expurgar_anteriores_a` nao tinha NENHUMA forma de ser executado.

    A docstring pedia uma operacao explicita, mas explicito sem interface e
    apenas inalcancavel.
    """

    async def test_previa_nao_apaga(self, client_admin):
        db_path = client_admin["db_path"]
        _entrada(db_path, dias_atras=400)
        corte = _ms(agora_utc_naive() - timedelta(days=365))

        resp = await client_admin["client"].post(f"/api/auditoria/expurgar?antes_de_ms={corte}")

        corpo = resp.json()
        assert corpo["executado"] is False
        assert corpo["seriam_removidas"] == 1
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] >= 1

    async def test_com_confirmar_apaga(self, client_admin):
        db_path = client_admin["db_path"]
        _entrada(db_path, dias_atras=400)
        corte = _ms(agora_utc_naive() - timedelta(days=365))

        resp = await client_admin["client"].post(
            f"/api/auditoria/expurgar?antes_de_ms={corte}&confirmar=true"
        )

        assert resp.json() == {"ok": True, "executado": True, "removidas": 1}

    async def test_expurgo_exige_admin(self, app_isolado, cabecalho_auth):
        transport = ASGITransport(app=app_isolado.app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=cabecalho_auth(username="enf1", role="enfermeiro"),
        ) as comum:
            resp = await comum.post("/api/auditoria/expurgar?antes_de_ms=1&confirmar=true")
        assert resp.status_code == 403

    async def test_consulta_informa_o_total(self, client_admin):
        """Trilha cortada em silencio produz resposta INCOMPLETA a uma
        pergunta legal ("quem acessou os dados deste titular?", LGPD Art. 18).
        """
        db_path = client_admin["db_path"]
        for _ in range(4):
            _entrada(db_path, dias_atras=1, usuario="ana")

        resp = await client_admin["client"].get("/api/auditoria?usuario=ana&limit=2")

        assert len(resp.json()) == 2
        assert resp.headers["X-Total-Count"] == "4"
