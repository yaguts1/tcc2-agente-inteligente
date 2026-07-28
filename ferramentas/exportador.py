"""Serviço de exportação de alertas em CSV e PDF."""

import io
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT

import structlog
from interface.dao import (
    selecionar_alertas_janela,
)

logger = structlog.get_logger(__name__)

# Timezone configuration
TZ_BR = ZoneInfo("America/Sao_Paulo")

# Janela usada quando o pedido nao traz datas — a mesma da tela de alertas.
JANELA_PADRAO_HORAS = 24


@dataclass
class ResultadoExport:
    """O que entrou no relatorio e, sobretudo, o que NAO entrou.

    Um relatorio de auditoria que omite linhas em silencio e pior que nenhum
    relatorio: quem o le acredita estar diante do conjunto completo e decide
    com base nisso. Havia duas omissoes invisiveis — truncamento por `limit` e
    descarte de alertas com `inicio` ilegivel — e o cabecalho ainda declarava
    "Periodo: Sem limite a Sem limite" sobre dados de 24h.
    """

    alertas: List[Dict[str, Any]]
    total_encontrado: int = 0
    truncado: bool = False
    ilegiveis: int = 0

    def __post_init__(self):
        if not self.total_encontrado:
            self.total_encontrado = len(self.alertas)

    def aviso(self) -> str | None:
        """Frase impressa no relatorio quando algo ficou de fora. None se nada ficou."""
        partes = []
        if self.truncado:
            partes.append(
                f"exibindo {len(self.alertas)} de {self.total_encontrado} alertas "
                "(limite da exportacao atingido)"
            )
        if self.ilegiveis:
            partes.append(
                f"{self.ilegiveis} alerta(s) com data de inicio ilegivel ficaram fora"
            )
        return "; ".join(partes) if partes else None


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
            resultado = self._get_alerts_for_export(filters)
            alerts = resultado.alertas

            self.logger.info(
                "csv_export",
                count=len(alerts),
                total_encontrado=resultado.total_encontrado,
                truncado=resultado.truncado,
                ilegiveis=resultado.ilegiveis,
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
            conteudo = csv_buffer.getvalue()

            # O aviso vai como comentario no fim do arquivo. Um CSV truncado e
            # visualmente identico a um completo; quem abre a planilha precisa
            # ver que faltam linhas.
            aviso = resultado.aviso()
            if aviso:
                conteudo += f"# AVISO: {aviso}\n"
            return conteudo
        
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
            resultado = self._get_alerts_for_export(filters)
            alerts = resultado.alertas

            self.logger.info(
                "pdf_export",
                count=len(alerts),
                total_encontrado=resultado.total_encontrado,
                truncado=resultado.truncado,
                ilegiveis=resultado.ilegiveis,
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
            self._generate_pdf(pdf_buffer, alerts, filters, resultado)
            
            return pdf_buffer.getvalue()
        
        except Exception as e:
            self.logger.error("pdf_export_error", error=str(e), filters=filters)
            raise
    
    def _get_alerts_for_export(self, filters: ExportFilters) -> "ResultadoExport":
        """
        Busca alertas do banco com os filtros aplicados.
        
        ✅ CORRIGIDO: Agora usa janela de 24h por padrão (consistente com dashboard)
        
        Comportamento:
        - Se start_date OU end_date especificados → busca todos e filtra manualmente
        - Senão → usa janela de 24h (padrão do dashboard)
        
        Args:
            filters: Filtros de exportação
        
        Returns:
            Lista de alertas como dicts
        """
        # ✅ CORRIGIDO: Usar janela consistente com dashboard
        # Se usuário especificar range de datas customizado, buscar todos
        # Senão, usar padrão de 24h (igual ao dashboard)
        if filters.start_date or filters.end_date:
            # Usuário quer range customizado - buscar todos e filtrar
            all_alerts = selecionar_alertas_janela(
                db_path=self.db_path,
                horas=None,  # Buscar todos para permitir filtro customizado
            )
        else:
            # Usar padrão de 24h (CONSISTENTE com dashboard e lista de alertas)
            all_alerts = selecionar_alertas_janela(
                db_path=self.db_path,
                horas=24,  # ✅ Mesma janela que dashboard usa
            )
        
        # Aplicar filtros de data, status e paciente
        filtered_alerts = []
        ilegiveis = 0
        for alert in all_alerts:
            # Filtro de data. `inicio` ilegivel NAO pode sumir do relatorio sem
            # deixar rastro: o `except: continue` original descartava a linha em
            # silencio, e um alerta real desaparecia de um documento de
            # auditoria sem nada indicando isso. Como nao da para afirmar que
            # ele pertence ao periodo pedido, ele fica de fora — mas CONTADO, e
            # a contagem sai impressa no relatorio.
            if filters.start_date or filters.end_date:
                alert_dt = None
                try:
                    alert_dt = datetime.fromisoformat(
                        str(alert.get('inicio', '')).replace('Z', '+00:00')
                    )
                except (ValueError, AttributeError):
                    alert_dt = None

                if alert_dt is None:
                    ilegiveis += 1
                    self.logger.warning(
                        "export_inicio_ilegivel",
                        paciente_id=alert.get('paciente_id'),
                        inicio=alert.get('inicio'),
                    )
                    continue
                if filters.start_date and alert_dt.date() < filters.start_date.date():
                    continue
                if filters.end_date and alert_dt.date() > filters.end_date.date():
                    continue

            # Filtrar por status se especificado
            # Mapear status do banco ('aberto', 'reconhecido', 'fechado') para o esperado ('pending', 'acknowledged', 'completed')
            status_map = {
                'aberto': 'pending',
                'reconhecido': 'acknowledged',
                'fechado': 'completed'
            }
            alert_status = status_map.get(alert.get('status', ''), alert.get('status'))
            if filters.status and alert_status != filters.status:
                continue
            
            # Filtrar por patient_id se especificado
            if filters.patient_id and alert.get('paciente_id') != filters.patient_id:
                continue
            
            filtered_alerts.append(alert)

        # O truncamento era invisivel: o laco parava em `limit` e devolvia a
        # lista, sem nada dizendo que havia mais. Um relatorio truncado tem a
        # mesma aparencia de um completo. Agora o corte e explicito e o total
        # encontrado acompanha o resultado.
        total = len(filtered_alerts)
        truncado = total > filters.limit
        return ResultadoExport(
            alertas=filtered_alerts[: filters.limit],
            total_encontrado=total,
            truncado=truncado,
            ilegiveis=ilegiveis,
        )
    
    def _generate_pdf(
        self,
        buffer: io.BytesIO,
        alerts: List[Dict[str, Any]],
        filters: ExportFilters,
        resultado: "ResultadoExport | None" = None,
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

        # O que ficou de fora, impresso ANTES da tabela: um relatorio truncado
        # e visualmente identico a um completo, e quem o le como evidencia
        # precisa saber que faltam linhas antes de tirar conclusoes.
        aviso = resultado.aviso() if resultado else None
        if aviso:
            story.append(Paragraph(f"<b>Atenção:</b> {aviso}.", subtitle_style))

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
        footer_text = f"Gerado em {datetime.now(TZ_BR).strftime('%d/%m/%Y %H:%M:%S')}"
        story.append(Paragraph(footer_text, subtitle_style))
        
        # Gerar PDF
        doc.build(story)
    
    def _format_date_range(self, filters: ExportFilters) -> str:
        """Formata o periodo para o cabecalho do relatorio.

        Sem datas, o cabecalho dizia "Periodo: Sem limite a Sem limite" — mas os
        dados vinham de uma janela de 24h. O documento declarava um escopo que
        nao era o dele, o que num relatorio usado como evidencia e pior que a
        ausencia de cabecalho.
        """
        if not filters.start_date and not filters.end_date:
            periodo = (
                f"<b>Período:</b> últimas {JANELA_PADRAO_HORAS} horas "
                "(inclui todos os alertas ainda em aberto, independentemente da idade)"
            )
        else:
            start_str = (
                filters.start_date.strftime("%d/%m/%Y") if filters.start_date else "Sem limite"
            )
            end_str = filters.end_date.strftime("%d/%m/%Y") if filters.end_date else "Sem limite"
            periodo = f"<b>Período:</b> {start_str} a {end_str}"

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

        return f"{periodo}{patient_str}{status_str}"
    
    def _prepare_table_data(self, alerts: List[Dict[str, Any]]) -> List[List[str]]:
        """Prepara dados para a tabela PDF."""
        # Buscar mapa de pacientes para substituir ID por Nome
        from interface.dao import listar_fichas_pacientes
        try:
            pacientes = listar_fichas_pacientes(self.db_path)
            paciente_map = {p["paciente_id"]: p["nome"] for p in pacientes}
        except Exception:
            paciente_map = {}

        # Cabeçalho
        header = [
            'Paciente',
            'Início',
            'Fim',
            'Tipo',
            'Perfil',
            'Status',
            'Duração',
            # "Concluído" sozinho nao diz se alguem virou o paciente ou se ele
            # se mexeu sozinho. Este relatorio e o que chega a coordenacao, e sem
            # esta coluna ele documenta adesao que talvez nunca tenha existido.
            'Resolvido por',
        ]
        
        data = [header]
        
        # Mapa de tradução de status
        status_map = {
            'aberto': 'Pendente',
            'reconhecido': 'Reconhecido',
            'fechado': 'Concluído'
        }
        
        # Mapa de tradução de perfil
        perfil_map = {
            'baixo': 'Baixo',
            'medio': 'Médio',
            'alto': 'Alto'
        }
        
        # Dados
        for alert in alerts:
            pid = str(alert.get('paciente_id', ''))
            nome_paciente = paciente_map.get(pid, pid)
            
            duracao = '-'
            if alert.get('duracao_min'):
                mins = int(alert.get('duracao_min'))
                if mins >= 60:
                    h = mins // 60
                    m = mins % 60
                    duracao = f"{h}h {m}min"
                else:
                    duracao = f"{mins} min"

            row = [
                nome_paciente,
                self._format_timestamp(alert.get('inicio')),
                self._format_timestamp(alert.get('fim')) if alert.get('fim') else '-',
                str(alert.get('tipo', '')).capitalize(),
                perfil_map.get(str(alert.get('perfil', '')).lower(), str(alert.get('perfil', ''))),
                status_map.get(str(alert.get('status', '')).lower(), str(alert.get('status', ''))),
                duracao,
                self._descrever_resolucao(alert),
            ]
            data.append(row)
        
        return data
    
    def _descrever_resolucao(self, alert: Dict[str, Any]) -> str:
        """Quem fechou o alerta, em texto para o relatorio.

        Tres respostas possiveis, e a terceira importa tanto quanto as outras:

          * a equipe (com o usuario, quando gravado);
          * o proprio paciente, que se mexeu sozinho — o motor detectou e fechou;
          * "nao registrado", para linhas anteriores a migrations/0007.

        O ultimo caso e deliberadamente visivel em vez de virar traco ou espaco
        em branco: quem le a planilha precisa saber que aquele periodo nao tem a
        informacao, e nao concluir que ninguem atendeu.
        """
        if not alert.get('fim'):
            return '-'

        origem = str(alert.get('origem_fechamento') or '').lower()
        if origem == 'equipe':
            quem = alert.get('fechado_por')
            return f"Equipe ({quem})" if quem else 'Equipe'
        if origem == 'sensor':
            return 'Movimento espontâneo'
        if origem == 'sistema':
            return 'Sistema'
        return 'Não registrado'

    def _create_table(self, data: List[List[str]]) -> Table:
        """Cria tabela formatada para PDF."""
        # Paciente, Início, Fim, Tipo, Perfil, Status, Duração, Resolvido por
        table = Table(
            data,
            colWidths=[1.6*inch, 1.15*inch, 1.15*inch, 0.85*inch, 0.7*inch, 0.9*inch, 0.9*inch, 1.35*inch],
        )
        
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
        """Formata timestamp para exibição (convertendo para horário local)."""
        if isinstance(ts, str):
            # Tentar fazer parse
            try:
                # Assumindo que o timestamp do banco está em UTC (termina em Z ou +00:00)
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                # Se não tiver timezone, assumir UTC (mesma regra do branch datetime abaixo,
                # em vez de depender implicitamente do fuso do sistema onde o código roda)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                # Converter para horário local
                dt_local = dt.astimezone(TZ_BR)
                return dt_local.strftime("%d/%m/%Y %H:%M")
            except (ValueError, TypeError):
                return ts[:16]
        elif isinstance(ts, datetime):
            # Se não tiver timezone, assumir UTC
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=ZoneInfo("UTC"))
            dt_local = ts.astimezone(TZ_BR)
            return dt_local.strftime("%d/%m/%Y %H:%M")
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
    
    parts.append(datetime.now(TZ_BR).strftime("%Y%m%d_%H%M"))
    
    return "_".join(parts) + ".csv"


def generate_pdf_filename(filters: ExportFilters) -> str:
    """Gera nome de arquivo para PDF."""
    parts = ["relatorio"]
    
    if filters.patient_id:
        parts.append(filters.patient_id)
    
    parts.append(datetime.now(TZ_BR).strftime("%Y-%m-%d_%H%M"))
    
    return "_".join(parts) + ".pdf"
