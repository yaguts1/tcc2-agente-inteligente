"""Testes unitários para o serviço de exportação."""

import pytest
from datetime import datetime
import os
import tempfile

from ferramentas.exportador import ExportFilters, ExportService, generate_csv_filename, generate_pdf_filename


class TestExportFilters:
    """Testes para a classe ExportFilters."""
    
    def test_validate_valid_filters(self):
        """Teste: Filtros válidos passam na validação."""
        filters = ExportFilters(
            start_date=datetime(2025, 10, 20),
            end_date=datetime(2025, 10, 27),
            status='pending',
            patient_id='PAC-0001',
        )
        valid, error = filters.validate()
        assert valid is True
        assert error is None
    
    def test_validate_empty_filters(self):
        """Teste: Filtros vazios são válidos."""
        filters = ExportFilters()
        valid, error = filters.validate()
        assert valid is True
        assert error is None
    
    def test_validate_invalid_date_range(self):
        """Teste: Data inicial > data final deve falhar."""
        filters = ExportFilters(
            start_date=datetime(2025, 10, 27),
            end_date=datetime(2025, 10, 20),
        )
        valid, error = filters.validate()
        assert valid is False
        assert "start_date não pode ser maior que end_date" in error
    
    def test_validate_invalid_status(self):
        """Teste: Status inválido deve falhar."""
        filters = ExportFilters(status='invalid_status')
        valid, error = filters.validate()
        assert valid is False
        assert "status deve ser um de:" in error
    
    def test_validate_valid_statuses(self):
        """Teste: Todos os status válidos devem passar."""
        for status in ['pending', 'acknowledged', 'completed']:
            filters = ExportFilters(status=status)
            valid, error = filters.validate()
            assert valid is True, f"Status '{status}' deve ser válido"
    
    def test_validate_invalid_limit_zero(self):
        """Teste: Limit zero deve falhar."""
        filters = ExportFilters(limit=0)
        valid, error = filters.validate()
        assert valid is False
        assert "limit deve estar entre 1 e 100000" in error
    
    def test_validate_invalid_limit_exceeded(self):
        """Teste: Limit > 100000 deve falhar."""
        filters = ExportFilters(limit=100001)
        valid, error = filters.validate()
        assert valid is False
        assert "limit deve estar entre 1 e 100000" in error
    
    def test_validate_valid_limit_boundaries(self):
        """Teste: Limites válidos devem passar."""
        for limit in [1, 100, 10000, 100000]:
            filters = ExportFilters(limit=limit)
            valid, error = filters.validate()
            assert valid is True, f"Limit {limit} deve ser válido"


class TestFilenameGeneration:
    """Testes para geração de nomes de arquivo."""
    
    def test_generate_csv_filename_no_filters(self):
        """Teste: Nome de CSV sem filtros."""
        filters = ExportFilters()
        filename = generate_csv_filename(filters)
        assert filename.startswith('alertas_')
        assert filename.endswith('.csv')
        assert len(filename) > 10
    
    def test_generate_csv_filename_with_dates(self):
        """Teste: Nome de CSV com datas."""
        filters = ExportFilters(
            start_date=datetime(2025, 10, 20),
            end_date=datetime(2025, 10, 27),
        )
        filename = generate_csv_filename(filters)
        assert '2025-10-20' in filename
        assert '2025-10-27' in filename
        assert filename.endswith('.csv')
    
    def test_generate_csv_filename_with_patient(self):
        """Teste: Nome de CSV com patient_id."""
        filters = ExportFilters(patient_id='PAC-0001')
        filename = generate_csv_filename(filters)
        assert 'PAC-0001' in filename
        assert filename.endswith('.csv')
    
    def test_generate_pdf_filename_no_filters(self):
        """Teste: Nome de PDF sem filtros."""
        filters = ExportFilters()
        filename = generate_pdf_filename(filters)
        assert filename.startswith('relatorio_')
        assert filename.endswith('.pdf')
    
    def test_generate_pdf_filename_with_patient(self):
        """Teste: Nome de PDF com patient_id."""
        filters = ExportFilters(patient_id='PAC-0001')
        filename = generate_pdf_filename(filters)
        assert 'PAC-0001' in filename
        assert filename.endswith('.pdf')


class TestExportServiceInitialization:
    """Testes para inicialização do ExportService."""
    
    def test_service_initialization(self):
        """Teste: Serviço deve inicializar com db_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            service = ExportService(db_path)
            assert service.db_path == db_path
            assert service.logger is not None


class TestExportServiceValidation:
    """Testes para validação no ExportService."""
    
    def test_export_csv_invalid_filters_raises_error(self):
        """Teste: CSV export com filtros inválidos deve lançar ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            service = ExportService(db_path)
            
            filters = ExportFilters(
                start_date=datetime(2025, 10, 27),
                end_date=datetime(2025, 10, 20),  # Data inválida
            )
            
            with pytest.raises(ValueError):
                service.export_to_csv(filters)
    
    def test_export_pdf_invalid_filters_raises_error(self):
        """Teste: PDF export com filtros inválidos deve lançar ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            service = ExportService(db_path)
            
            filters = ExportFilters(status='invalid')
            
            with pytest.raises(ValueError):
                service.export_to_pdf(filters)


class TestFilenameFormatting:
    """Testes para funções de formatação."""
    
    def test_format_timestamp_with_string(self):
        """Teste: Formatar timestamp string sem timezone (assumido como UTC, convertido p/ America/Sao_Paulo)."""
        service = ExportService(':memory:')
        ts = '2025-10-27T14:30:00'
        result = service._format_timestamp(ts)
        assert '27/10/2025' in result
        assert '11:30' in result

    def test_format_timestamp_with_datetime(self):
        """Teste: Formatar timestamp datetime sem timezone (assumido como UTC, convertido p/ America/Sao_Paulo)."""
        service = ExportService(':memory:')
        ts = datetime(2025, 10, 27, 14, 30, 0)
        result = service._format_timestamp(ts)
        assert '27/10/2025' in result
        assert '11:30' in result
    
    def test_translate_status(self):
        """Teste: Traduzir status."""
        service = ExportService(':memory:')
        assert service._translate_status('pending') == 'Pendente'
        assert service._translate_status('acknowledged') == 'Reconhecido'
        assert service._translate_status('completed') == 'Concluído'
        assert service._translate_status('unknown') == 'unknown'


class TestEdgeCases:
    """Testes para edge cases."""
    
    def test_filters_same_date(self):
        """Teste: Data inicial = data final deve ser válida."""
        date = datetime(2025, 10, 27)
        filters = ExportFilters(start_date=date, end_date=date)
        valid, error = filters.validate()
        assert valid is True
    
    def test_filters_large_date_range(self):
        """Teste: Range de data muito grande deve ser válida."""
        filters = ExportFilters(
            start_date=datetime(1990, 1, 1),
            end_date=datetime(2099, 12, 31),
        )
        valid, error = filters.validate()
        assert valid is True
    
    def test_filters_special_characters_in_patient_id(self):
        """Teste: Patient ID com caracteres especiais."""
        filters = ExportFilters(patient_id='PAC-0001-SPECIAL!@#')
        valid, error = filters.validate()
        # Deve ser válido - validação específica de patient_id não existe
        assert valid is True
    
    def test_filters_empty_patient_id(self):
        """Teste: Patient ID vazio é None."""
        filters = ExportFilters(patient_id='')
        # Empty string não é None, mas é falsy
        assert filters.patient_id == ''
        valid, error = filters.validate()
        assert valid is True
    
    def test_export_with_max_limit(self):
        """Teste: Export com limite máximo."""
        filters = ExportFilters(limit=100000)
        valid, error = filters.validate()
        assert valid is True
    
    def test_export_with_min_limit(self):
        """Teste: Export com limite mínimo."""
        filters = ExportFilters(limit=1)
        valid, error = filters.validate()
        assert valid is True


class TestDataFormatting:
    """Testes para formatação de dados."""
    
    def test_format_date_range_no_dates(self):
        """Teste: Formatar date range sem datas."""
        service = ExportService(':memory:')
        filters = ExportFilters()
        result = service._format_date_range(filters)
        assert 'Sem limite' in result
    
    def test_format_date_range_with_dates(self):
        """Teste: Formatar date range com datas."""
        service = ExportService(':memory:')
        filters = ExportFilters(
            start_date=datetime(2025, 10, 20),
            end_date=datetime(2025, 10, 27),
        )
        result = service._format_date_range(filters)
        assert '20/10/2025' in result
        assert '27/10/2025' in result
    
    def test_format_date_range_with_patient(self):
        """Teste: Formatar date range com patient."""
        service = ExportService(':memory:')
        filters = ExportFilters(patient_id='PAC-0001')
        result = service._format_date_range(filters)
        assert 'PAC-0001' in result
    
    def test_format_date_range_with_status(self):
        """Teste: Formatar date range com status."""
        service = ExportService(':memory:')
        filters = ExportFilters(status='pending')
        result = service._format_date_range(filters)
        assert 'Pendente' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
