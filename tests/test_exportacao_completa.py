"""O relatorio precisa dizer o que ele e.

Um relatorio de auditoria que omite linhas em silencio e pior que nenhum
relatorio: quem o le acredita estar diante do conjunto completo e decide com
base nisso. Havia duas omissoes invisiveis e uma afirmacao falsa:

1. o truncamento por `limit` parava o laco e devolvia a lista, sem nada
   indicando que havia mais — um relatorio truncado e visualmente identico a um
   completo;
2. um alerta com `inicio` ilegivel caia num `except: continue` e sumia do
   documento sem deixar rastro;
3. sem datas no pedido, o cabecalho declarava "Periodo: Sem limite a Sem
   limite" enquanto os dados vinham de uma janela de 24h.
"""

import sqlite3
from datetime import timedelta

import pytest

from ferramentas.exportador import ExportFilters, ExportService
from interface.dao import inserir_alertas
from interface.db_core import criar_esquema
from interface.tempo import agora_utc_naive

AGORA = agora_utc_naive()


@pytest.fixture
def servico(tmp_path):
    db = str(tmp_path / "t.db")
    criar_esquema(db)
    for i in range(5):
        inicio = (AGORA - timedelta(hours=i + 1)).strftime("%Y-%m-%dT%H:%M:%S")
        inserir_alertas(db, [{
            "paciente_id": f"PAC-{i}",
            "inicio": inicio,
            "fim": inicio,
            "tipo": "imobilidade",
            "perfil": "alto",
            "janela_min": 60,
            "status": "fechado",
            "duracao_min": 10.0,
        }])
    return ExportService(db)


def test_truncamento_e_declarado(servico):
    """5 alertas, limite 3: o relatorio precisa dizer que faltam 2."""
    resultado = servico._get_alerts_for_export(ExportFilters(limit=3))

    assert len(resultado.alertas) == 3
    assert resultado.total_encontrado == 5
    assert resultado.truncado is True
    assert "3 de 5" in resultado.aviso()


def test_sem_truncamento_nao_ha_aviso(servico):
    """Aviso so quando ha algo a avisar — ruido constante deixa de ser lido."""
    resultado = servico._get_alerts_for_export(ExportFilters(limit=100))

    assert resultado.truncado is False
    assert resultado.aviso() is None


def test_csv_truncado_carrega_o_aviso(servico):
    """Uma planilha truncada e identica a uma completa aos olhos de quem abre."""
    conteudo = servico.export_to_csv(ExportFilters(limit=2))

    avisos = [linha for linha in conteudo.splitlines() if linha.startswith("# AVISO")]
    assert len(avisos) == 1
    assert "2 de 5" in avisos[0]


def test_alerta_com_inicio_ilegivel_e_contado_e_nao_sumido(servico):
    """Antes o `except: continue` fazia a linha desaparecer sem rastro."""
    with sqlite3.connect(servico.db_path) as conn:
        conn.execute("UPDATE alertas SET inicio='data-corrompida' WHERE paciente_id='PAC-2'")

    resultado = servico._get_alerts_for_export(
        ExportFilters(start_date=AGORA - timedelta(days=2))
    )

    assert resultado.ilegiveis == 1
    assert "ilegivel" in resultado.aviso()
    assert len(resultado.alertas) == 4


def test_cabecalho_declara_a_janela_real(servico):
    """Sem datas, o relatorio cobre 24h — e tem de dizer isso, nao 'sem limite'."""
    cabecalho = servico._format_date_range(ExportFilters())

    assert "24 horas" in cabecalho
    assert "Sem limite" not in cabecalho


def test_cabecalho_com_datas_mostra_o_intervalo_pedido(servico):
    inicio = AGORA - timedelta(days=3)
    cabecalho = servico._format_date_range(
        ExportFilters(start_date=inicio, end_date=AGORA)
    )

    assert inicio.strftime("%d/%m/%Y") in cabecalho
    assert "24 horas" not in cabecalho


def test_alerta_aberto_antigo_entra_no_relatorio(servico):
    """Coerencia com a tela: alerta nao resolvido ignora a janela.

    Se o relatorio omitisse o paciente mais atrasado, ele contradiria o que a
    equipe ve — e a divergencia so apareceria numa auditoria.
    """
    antigo = (AGORA - timedelta(hours=50)).strftime("%Y-%m-%dT%H:%M:%S")
    inserir_alertas(servico.db_path, [{
        "paciente_id": "PAC-ANTIGO",
        "inicio": antigo,
        "fim": None,
        "tipo": "imobilidade",
        "perfil": "alto",
        "janela_min": 60,
        "status": "aberto",
        "duracao_min": None,
    }])

    resultado = servico._get_alerts_for_export(ExportFilters())

    assert any(a["paciente_id"] == "PAC-ANTIGO" for a in resultado.alertas)


def test_pdf_sai_com_o_aviso_sem_estourar(servico):
    """O PDF e gerado por reportlab; o aviso nao pode quebrar a montagem."""
    pdf = servico.export_to_pdf(ExportFilters(limit=2))

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
