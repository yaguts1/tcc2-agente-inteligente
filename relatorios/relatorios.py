"""Geração de relatórios a partir dos dados persistidos."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Sequence, Tuple

import pandas as pd
from fpdf import FPDF

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _selecionar_alertas_periodo(
    conn: sqlite3.Connection,
    horas: int,
) -> Tuple[List[sqlite3.Row], datetime]:
    """Obtém alertas cujo início está dentro da janela solicitada.

    Args:
        conn: Conexão SQLite aberta.
        horas: Número de horas retroativas a considerar.

    Returns:
        Tupla ``(linhas, agora)`` com os registros filtrados e o timestamp de geração.
    """
    agora = datetime.now().replace(microsecond=0)
    inicio_janela = agora - timedelta(hours=horas)
    cursor = conn.execute(
        """
        SELECT paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min
        FROM alertas
        WHERE inicio BETWEEN ? AND ?
        ORDER BY inicio
        """,
        (
            inicio_janela.strftime(ISO_FORMAT),
            agora.strftime(ISO_FORMAT),
        ),
    )
    linhas = cursor.fetchall()
    return linhas, agora


def exportar_csv_alertas(db_path: str, destino: str, horas: int = 24) -> int:
    """Exporta alertas recentes para CSV.

    Args:
        db_path: Caminho para o arquivo SQLite.
        destino: Caminho do arquivo CSV de saída.
        horas: Janela retroativa em horas.

    Returns:
        Quantidade de linhas exportadas.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        linhas, _ = _selecionar_alertas_periodo(conn, horas)

    colunas: Sequence[str] = (
        "paciente_id",
        "inicio",
        "fim",
        "tipo",
        "perfil",
        "janela_min",
        "status",
        "duracao_min",
    )
    df = pd.DataFrame(linhas, columns=colunas) if linhas else pd.DataFrame(columns=colunas)

    destino_path = Path(destino)
    destino_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino_path, index=False, encoding="utf-8")
    return len(df)


def exportar_pdf_resumo(db_path: str, destino: str, horas: int = 24) -> None:
    """Gera PDF de resumo de alertas abertos e fechados no período.

    Args:
        db_path: Caminho para o arquivo SQLite.
        destino: Caminho do arquivo PDF de saída.
        horas: Janela retroativa em horas.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        linhas, agora = _selecionar_alertas_periodo(conn, horas)

    destino_path = Path(destino)
    destino_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF(unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Relatório de Alertas", ln=1)

    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, f"Gerado em: {agora.strftime(ISO_FORMAT)}", ln=1)
    pdf.cell(0, 8, f"Janela: últimas {horas} horas", ln=1)
    pdf.cell(0, 8, f"Total de alertas: {len(linhas)}", ln=1)
    pdf.ln(4)

    headers = ["Paciente", "Início", "Fim", "Status"]
    col_widths = [40, 50, 50, 30]

    pdf.set_font("Helvetica", "B", 11)
    for header, width in zip(headers, col_widths):
        pdf.cell(width, 8, header, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", size=10)
    for row in linhas:
        values = [
            str(row["paciente_id"] or ""),
            str(row["inicio"] or ""),
            str(row["fim"] or ""),
            str(row["status"] or ""),
        ]
        for value, width in zip(values, col_widths):
            pdf.cell(width, 7, value, border=1)
        pdf.ln()

    pdf.output(destino_path.as_posix())
