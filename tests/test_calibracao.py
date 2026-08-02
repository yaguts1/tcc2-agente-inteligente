"""Calibração: a confiança do sensor prediz falso alarme?

`grade.confianca` era gravada em toda amostra e **nunca lida**. O botão "falso
alarme" já existia no fechamento, então o dado do outro lado também já vinha
sendo coletado — faltava alguém somar os dois. Enquanto isso, "qual a taxa de
falso-positivo desta instalação?" só tinha uma resposta honesta: não sei.

O que estes testes protegem não é a aritmética (é uma divisão), e sim as
DECISÕES em volta dela — quais alertas entram na conta, o que conta como falso
positivo, e o que o relatório diz quando não sabe.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from interface.db_core import criar_esquema
from interface.repositories.calibracao import calibracao
from interface.tempo import agora_utc_naive


@pytest.fixture()
def banco(tmp_path):
    caminho = str(tmp_path / "calibracao.db")
    criar_esquema(caminho)
    return caminho


def _alerta(
    banco: str,
    paciente_id: str,
    minutos_atras: int,
    *,
    confianca: float | None,
    motivo: str | None,
    status: str = "fechado",
    janela_min: int = 60,
    amostras: int = 6,
) -> None:
    """Cria um alerta e as amostras da janela que o teria gerado."""
    inicio = agora_utc_naive() - timedelta(minutes=minutos_atras)
    inicio_iso = inicio.strftime("%Y-%m-%dT%H:%M:%S")

    with sqlite3.connect(banco) as conn:
        conn.execute("INSERT OR IGNORE INTO pacientes (id) VALUES (?)", (paciente_id,))
        conn.execute(
            "INSERT INTO alertas (paciente_id, inicio, tipo, perfil, janela_min, status,"
            " motivo_fechamento) VALUES (?,?,?,?,?,?,?)",
            (paciente_id, inicio_iso, "imobilidade", "alto", janela_min, status, motivo),
        )
        if confianca is not None:
            passo = janela_min / max(1, amostras)
            for i in range(amostras):
                ts = inicio - timedelta(minutes=janela_min - i * passo)
                conn.execute(
                    "INSERT OR REPLACE INTO grade (paciente_id, ts, ts_ms, postura, confianca)"
                    " VALUES (?,?,?,?,?)",
                    (
                        paciente_id,
                        ts.strftime("%Y-%m-%dT%H:%M:%S"),
                        int(ts.timestamp() * 1000),
                        "supino",
                        confianca,
                    ),
                )
        conn.commit()


class TestQuemEntraNaConta:
    def test_alerta_aberto_nao_entra(self, banco):
        """Ninguém julgou ainda. Contá-lo como verdadeiro inflaria a qualidade
        aparente do sistema — que é justamente o erro que este relatório existe
        para não cometer."""
        _alerta(banco, "PAC-A", 30, confianca=0.95, motivo=None, status="aberto")

        r = calibracao(banco)

        assert r["alertas_classificados"] == 0
        assert r["taxa_falso_alarme"] is None

    def test_fechado_sem_motivo_nao_entra(self, banco):
        """Fechado sem justificativa não diz se era verdadeiro."""
        _alerta(banco, "PAC-B", 30, confianca=0.95, motivo=None, status="fechado")

        assert calibracao(banco)["alertas_classificados"] == 0

    def test_fora_da_janela_de_dias_nao_entra(self, banco):
        _alerta(banco, "PAC-C", 60 * 24 * 40, confianca=0.95, motivo="falso_alarme")

        assert calibracao(banco, dias=30)["alertas_classificados"] == 0
        assert calibracao(banco, dias=60)["alertas_classificados"] == 1


class TestOQueContaComoFalsoPositivo:
    def test_so_falso_alarme_conta(self, banco):
        """`em_procedimento`, `recusa_do_paciente` e `contraindicado` são
        alertas CORRETOS cuja ação não pôde ser executada. Contá-los como
        falso-positivo culparia o sensor por uma decisão clínica."""
        _alerta(banco, "PAC-1", 10, confianca=0.95, motivo="falso_alarme")
        _alerta(banco, "PAC-2", 20, confianca=0.95, motivo="em_procedimento")
        _alerta(banco, "PAC-3", 30, confianca=0.95, motivo="recusa_do_paciente")
        _alerta(banco, "PAC-4", 40, confianca=0.95, motivo="contraindicado")
        _alerta(banco, "PAC-5", 50, confianca=0.95, motivo="reposicionado")

        r = calibracao(banco)

        assert r["alertas_classificados"] == 5
        assert r["falsos_alarmes"] == 1
        assert r["taxa_falso_alarme"] == 0.2


class TestFaixasDeConfianca:
    def test_alerta_cai_na_faixa_da_media_das_amostras(self, banco):
        _alerta(banco, "PAC-BAIXA", 10, confianca=0.65, motivo="falso_alarme")
        _alerta(banco, "PAC-ALTA", 20, confianca=0.97, motivo="reposicionado")

        faixas = {f["faixa"]: f for f in calibracao(banco)["por_faixa"]}

        assert faixas["<0.70"]["alertas"] == 1
        assert faixas["<0.70"]["taxa"] == 1.0
        assert faixas[">=0.90"]["alertas"] == 1
        assert faixas[">=0.90"]["taxa"] == 0.0

    def test_faixa_vazia_diz_None_e_nao_zero(self, banco):
        """"Não sei" e "zero por cento" são afirmações diferentes, e a segunda
        seria mentira num relatório de calibração."""
        _alerta(banco, "PAC-X", 10, confianca=0.95, motivo="reposicionado")

        faixas = {f["faixa"]: f for f in calibracao(banco)["por_faixa"]}

        assert faixas["<0.70"]["alertas"] == 0
        assert faixas["<0.70"]["taxa"] is None

    def test_alerta_sem_amostras_e_contado_a_parte(self, banco):
        """Amostras fora da retenção, ou instalação anterior à coluna
        `confianca`. Jogá-lo numa faixa seria inventar dado."""
        _alerta(banco, "PAC-SEM", 10, confianca=None, motivo="falso_alarme")

        r = calibracao(banco)

        assert r["sem_amostras"] == 1
        assert r["alertas_classificados"] == 1  # segue contando na taxa global
        assert sum(f["alertas"] for f in r["por_faixa"]) == 0


class TestARespostaQueOTccPrecisa:
    def test_confianca_baixa_com_mais_falso_alarme_fica_visivel(self, banco):
        """O relatório inteiro existe para esta pergunta: o limiar está no lugar
        certo? Aqui a resposta é "as faixas baixas erram mais", e ela aparece
        sem ninguém precisar abrir o banco."""
        for i in range(4):
            _alerta(banco, f"PAC-B{i}", 10 + i, confianca=0.65, motivo="falso_alarme")
        _alerta(banco, "PAC-B9", 20, confianca=0.65, motivo="reposicionado")
        for i in range(9):
            _alerta(banco, f"PAC-A{i}", 30 + i, confianca=0.95, motivo="reposicionado")
        _alerta(banco, "PAC-A9", 45, confianca=0.95, motivo="falso_alarme")

        faixas = {f["faixa"]: f for f in calibracao(banco)["por_faixa"]}

        assert faixas["<0.70"]["taxa"] == 0.8
        assert faixas[">=0.90"]["taxa"] == 0.1
        assert faixas["<0.70"]["taxa"] > faixas[">=0.90"]["taxa"]

    def test_o_relatorio_carrega_o_denominador(self, banco):
        """Com poucos alertas classificados, qualquer taxa é ruído. Quem lê
        precisa ver o volume junto do número, senão mexe no limiar por causa de
        dois casos."""
        _alerta(banco, "PAC-U", 10, confianca=0.95, motivo="falso_alarme")

        r = calibracao(banco)

        assert r["taxa_falso_alarme"] == 1.0
        assert r["alertas_classificados"] == 1, "o denominador precisa vir junto"


class TestPelaRota:
    """A regra vale, mas quem responde é o endpoint. Um relatório correto atrás
    de uma rota quebrada não informa ninguém."""

    @pytest.mark.asyncio
    async def test_rota_devolve_o_relatorio(self, app_isolado, cabecalho_auth):
        from httpx import ASGITransport, AsyncClient

        _alerta(app_isolado.db_path, "PAC-ROTA", 15, confianca=0.62, motivo="falso_alarme")

        transport = ASGITransport(app=app_isolado.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/api/relatorios/calibracao", headers=cabecalho_auth())

        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["alertas_classificados"] == 1
        assert corpo["taxa_falso_alarme"] == 1.0
        faixas = {f["faixa"]: f for f in corpo["por_faixa"]}
        assert faixas["<0.70"]["alertas"] == 1

    @pytest.mark.asyncio
    async def test_rota_exige_sessao(self, app_isolado):
        """É inteligência operacional sobre uma unidade de saúde: quantos alertas
        a instalação emite e quantos são falsos. Não sai para anônimo."""
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app_isolado.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/api/relatorios/calibracao")

        assert resp.status_code in (401, 403), f"veio {resp.status_code}"


class TestEscopoPorUnidade:
    """A rota já recebia `escopo_de_unidades` e o cálculo IGNORAVA.

    Não era só cosmético: uma taxa misturando alas responde à pergunta errada —
    a enfermeira de uma ala decidiria limiar com o número de outra — e ainda
    vaza volume de alerta de unidade alheia por uma porta lateral.
    """

    def _com_unidade(self, banco: str, paciente_id: str, unidade_id: int) -> None:
        agora = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")
        with sqlite3.connect(banco) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO paciente_fichas"
                " (paciente_id, nome, perfil, unidade_id, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (paciente_id, paciente_id, "alto", unidade_id, agora, agora),
            )
            conn.commit()

    def test_escopo_exclui_alerta_de_outra_unidade(self, banco):
        _alerta(banco, "PAC-U1", 10, confianca=0.95, motivo="falso_alarme")
        _alerta(banco, "PAC-U2", 20, confianca=0.95, motivo="reposicionado")
        self._com_unidade(banco, "PAC-U1", 1)
        self._com_unidade(banco, "PAC-U2", 2)

        assert calibracao(banco, unidades={1})["alertas_classificados"] == 1
        assert calibracao(banco, unidades={2})["alertas_classificados"] == 1
        assert calibracao(banco, unidades={1, 2})["alertas_classificados"] == 2

    def test_admin_ve_a_instalacao_inteira(self, banco):
        """`unidades is None` = admin. Mesma regra de `alerts_service`."""
        _alerta(banco, "PAC-U1", 10, confianca=0.95, motivo="falso_alarme")
        self._com_unidade(banco, "PAC-U1", 1)

        assert calibracao(banco, unidades=None)["alertas_classificados"] == 1

    def test_escopo_vazio_nao_e_zero_por_cento(self, banco):
        """Usuário sem unidade nenhuma não tem "zero de falso alarme": não tem
        dado. A diferença importa num relatório de calibração."""
        _alerta(banco, "PAC-U1", 10, confianca=0.95, motivo="falso_alarme")
        self._com_unidade(banco, "PAC-U1", 1)

        r = calibracao(banco, unidades=set())

        assert r["alertas_classificados"] == 0
        assert r["taxa_falso_alarme"] is None
