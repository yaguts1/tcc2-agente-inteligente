"""Serviço de exportação de alertas em CSV e PDF."""

import io
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT

import structlog
from interface.dao import (
    selecionar_alertas_janela,
    obter_usuario_por_nome,
)

logger = structlog.get_logger(__name__)


class ExportFilters:
    """Filtros para exportação de alertas."""
    
    def __init__(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status: Optional[str] = None,
        patient_id: Optional[str] = None,
        limit: int = 10000,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.status = status
        self.patient_id = patient_id
        self.limit = limit
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """Valida os filtros."""
        # Validar range de datas
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                return False, "start_date não pode ser maior que end_date"
        
        # Validar status
        valid_statuses = ['pending', 'acknowledged', 'completed']
        if self.status and self.status not in valid_statuses:
            return False, f"status deve ser um de: {', '.join(valid_statuses)}"
        
        # Validar limit
        if self.limit <= 0 or self.limit > 100000:
            return False, "limit deve estar entre 1 e 100000"
        
        return True, None


class ExportService:
    """Serviço para exportação de alertas."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logger
    
    def export_to_csv(self, filters: ExportFilters, username: str = "sistema") -> str:
        """
        Exporta alertas para CSV.
        
        Args:
            filters: Filtros de exportação
            username: Usuário fazendo a requisição (para logging)
        
        Returns:
            String com conteúdo CSV
        
        Raises:
            ValueError: Se filtros inválidos
        """
        # Validar filtros
        valid, error = filters.validate()
        if not valid:
            raise ValueError(f"Filtros inválidos: {error}")
        
        try:
            # Buscar alertas
            alerts = self._get_alerts_for_export(filters)
            
            self.logger.info(
                "csv_export",
                count=len(alerts),
                filters={
                    "start_date": filters.start_date.isoformat() if filters.start_date else None,
                    "end_date": filters.end_date.isoformat() if filters.end_date else None,
                    "status": filters.status,
                    "patient_id": filters.patient_id,
                },
                user=username,
            )
            
            # Converter para DataFrame
            if not alerts:
                df = pd.DataFrame()
            else:
                df = pd.DataFrame(alerts)
            
            # Retornar CSV
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8')
            return csv_buffer.getvalue()
        
        except Exception as e:
            self.logger.error("csv_export_error", error=str(e), filters=filters)
            raise
    
    def export_to_pdf(self, filters: ExportFilters, username: str = "sistema") -> bytes:
        """
        Exporta alertas para PDF.
        
        Args:
            filters: Filtros de exportação
            username: Usuário fazendo a requisição (para logging)
        
        Returns:
            Bytes com conteúdo PDF
        
        Raises:
            ValueError: Se filtros inválidos
        """
        # Validar filtros
        valid, error = filters.validate()
        if not valid:
            raise ValueError(f"Filtros inválidos: {error}")
        
        try:
            # Buscar alertas
            alerts = self._get_alerts_for_export(filters)
            
            self.logger.info(
                "pdf_export",
                count=len(alerts),
                filters={
                    "start_date": filters.start_date.isoformat() if filters.start_date else None,
                    "end_date": filters.end_date.isoformat() if filters.end_date else None,
                    "status": filters.status,
                    "patient_id": filters.patient_id,
                },
                user=username,
            )
            
            # Gerar PDF
            pdf_buffer = io.BytesIO()
            self._generate_pdf(pdf_buffer, alerts, filters)
            
            return pdf_buffer.getvalue()
        
        except Exception as e:
            self.logger.error("pdf_export_error", error=str(e), filters=filters)
            raise
    
    def _get_alerts_for_export(self, filters: ExportFilters) -> List[Dict[str, Any]]:
        """
        Busca alertas do banco com os filtros aplicados.
        
        Args:
            filters: Filtros de exportação
        
        Returns:
            Lista de alertas como dicts
        """
        # Buscar alertas usando a função do DAO
        alerts = selecionar_alertas_janela(
            db_path=self.db_path,
            inicio=filters.start_date,
            fim=filters.end_date,
            limit=filters.limit,
        )
        
        # Aplicar filtros de status e paciente
        filtered_alerts = []
        for alert in alerts:
            # Filtrar por status se especificado
            if filters.status and alert.get('status') != filters.status:
                continue
            
            # Filtrar por patient_id se especificado
            if filters.patient_id and alert.get('patient_id') != filters.patient_id:
                continue
            
            filtered_alerts.append(alert)
        
        return filtered_alerts
    
    def _generate_pdf(
        self,
        buffer: io.BytesIO,
        alerts: List[Dict[str, Any]],
        filters: ExportFilters,
    ) -> None:
        """
        Gera PDF com os alertas.
        
        Args:
            buffer: Buffer para escrever o PDF
            alerts: Lista de alertas
            filters: Filtros aplicados
        """
        # Configurar documento
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch,
        )
        
        # Container para elementos
        story = []
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1f2937'),
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=12,
            alignment=TA_LEFT,
        )
        
        # Título
        story.append(Paragraph("Relatório de Alertas - UPP", title_style))
        
        # Data range
        date_str = self._format_date_range(filters)
        story.append(Paragraph(date_str, subtitle_style))
        
        story.append(Spacer(1, 0.2*inch))
        
        # Tabela
        if alerts:
            table_data = self._prepare_table_data(alerts)
            table = self._create_table(table_data)
            story.append(table)
        else:
            story.append(Paragraph("<b>Nenhum alerta encontrado para os filtros selecionados.</b>", styles['Normal']))
        
        story.append(Spacer(1, 0.2*inch))
        
        # Footer
        footer_text = f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        story.append(Paragraph(footer_text, subtitle_style))
        
        # Gerar PDF
        doc.build(story)
    
    def _format_date_range(self, filters: ExportFilters) -> str:
        """Formata o range de datas para exibição."""
        start_str = "Sem limite"
        end_str = "Sem limite"
        
        if filters.start_date:
            start_str = filters.start_date.strftime("%d/%m/%Y")
        
        if filters.end_date:
            end_str = filters.end_date.strftime("%d/%m/%Y")
        
        patient_str = ""
        if filters.patient_id:
            patient_str = f" • Paciente: {filters.patient_id}"
        
        status_str = ""
        if filters.status:
            status_map = {
                'pending': 'Pendente',
                'acknowledged': 'Reconhecido',
                'completed': 'Concluído',
            }
            status_str = f" • Status: {status_map.get(filters.status, filters.status)}"
        
        return f"<b>Período:</b> {start_str} a {end_str}{patient_str}{status_str}"
    
    def _prepare_table_data(self, alerts: List[Dict[str, Any]]) -> List[List[str]]:
        """Prepara dados para a tabela PDF."""
        # Cabeçalho
        header = [
            'ID',
            'Data/Hora',
            'Tipo',
            'Severidade',
            'Status',
            'Paciente',
            'Observação',
        ]
        
        data = [header]
        
        # Dados
        for alert in alerts:
            row = [
                str(alert.get('alert_id', '')),
                self._format_timestamp(alert.get('alert_timestamp')),
                str(alert.get('alert_type', '')),
                str(alert.get('severity', '')),
                self._translate_status(alert.get('status', '')),
                str(alert.get('patient_id', '')),
                str(alert.get('observacao', ''))[:50],  # Limitar a 50 caracteres
            ]
            data.append(row)
        
        return data
    
    def _create_table(self, data: List[List[str]]) -> Table:
        """Cria tabela formatada para PDF."""
        table = Table(data, colWidths=[0.6*inch, 1.2*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 1.8*inch])
        
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            
            # Dados
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        return table
    
    def _format_timestamp(self, ts: Any) -> str:
        """Formata timestamp para exibição."""
        if isinstance(ts, str):
            # Tentar fazer parse
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.strftime("%d/%m/%Y %H:%M")
            except:
                return ts[:16]
        elif isinstance(ts, datetime):
            return ts.strftime("%d/%m/%Y %H:%M")
        else:
            return str(ts)
    
    def _translate_status(self, status: str) -> str:
        """Traduz status para português."""
        translations = {
            'pending': 'Pendente',
            'acknowledged': 'Reconhecido',
            'completed': 'Concluído',
        }
        return translations.get(status, status)


def generate_csv_filename(filters: ExportFilters) -> str:
    """Gera nome de arquivo para CSV."""
    parts = ["alertas"]
    
    if filters.start_date:
        parts.append(filters.start_date.strftime("%Y-%m-%d"))
    
    if filters.end_date:
        parts.append(filters.end_date.strftime("%Y-%m-%d"))
    
    if filters.patient_id:
        parts.append(filters.patient_id)
    
    parts.append(datetime.now().strftime("%Y%m%d"))
    
    return "_".join(parts) + ".csv"


def generate_pdf_filename(filters: ExportFilters) -> str:
    """Gera nome de arquivo para PDF."""
    parts = ["relatorio"]
    
    if filters.patient_id:
        parts.append(filters.patient_id)
    
    parts.append(datetime.now().strftime("%Y-%m-%d"))
    
    return "_".join(parts) + ".pdf"
