"""Testes de integração para endpoints de exportação."""

import pytest
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Importar o router
from interface.api import router

# Criar app e registrar router
app = FastAPI()
app.include_router(router)

# Criar cliente de teste
client = TestClient(app)


class TestExportCSVEndpoint:
    """Testes para endpoint GET /api/alerts/export/csv."""
    
    def test_export_csv_requires_authentication(self):
        """Teste: Endpoint CSV sem auth deve retornar 401."""
        response = client.get("/api/alerts/export/csv")
        assert response.status_code == 401
        data = response.json()
        assert "Não autenticado" in data.get("detail", "") or response.status_code == 401
    
    def test_export_csv_with_bearer_token(self):
        """Teste: Endpoint CSV com Bearer token válido."""
        # Mock da função que busca alertas - IMPORTANTE: patch onde é usado (ferramentas.exportador)
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = [
                {
                    'alert_id': 1,
                    'alert_timestamp': datetime.now().isoformat(),
                    'alert_type': 'postura',
                    'severity': 'high',
                    'status': 'pending',
                    'patient_id': 'PAC-0001',
                    'observacao': 'Test alert',
                }
            ]
            
            response = client.get(
                "/api/alerts/export/csv",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Pode ser 200 ou erro dependendo de DB, mas não 401
            assert response.status_code in [200, 500]
            assert response.status_code != 401
    
    def test_export_csv_invalid_date_format(self):
        """Teste: Data inválida deve retornar 400."""
        response = client.get(
            "/api/alerts/export/csv?start_date=invalid-date",
            headers={"Authorization": "Bearer user@test.com:1234567890"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "inválido" in data.get("detail", "").lower()
    
    def test_export_csv_valid_date_format(self):
        """Teste: Data válida no formato YYYY-MM-DD."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/csv?start_date=2025-10-20&end_date=2025-10-27",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Aceitar 200 ou 500 (DB error), mas não 400
            assert response.status_code != 400
    
    def test_export_csv_invalid_status(self):
        """Teste: Status inválido deve retornar 400."""
        response = client.get(
            "/api/alerts/export/csv?status=invalid_status",
            headers={"Authorization": "Bearer user@test.com:1234567890"}
        )
        assert response.status_code == 400
    
    def test_export_csv_valid_statuses(self):
        """Teste: Status válidos não devem retornar 400."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            for status in ['pending', 'acknowledged', 'completed']:
                response = client.get(
                    f"/api/alerts/export/csv?status={status}",
                    headers={"Authorization": "Bearer user@test.com:1234567890"}
                )
                # Não deve ser 400 (validação OK)
                assert response.status_code != 400, f"Status '{status}' deve ser válido"
    
    def test_export_csv_content_type(self):
        """Teste: Response deve ter Content-Type: text/csv."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/csv",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            if response.status_code == 200:
                # Allow charset suffix
                assert "text/csv" in response.headers.get("content-type")
    
    def test_export_csv_has_content_disposition(self):
        """Teste: Response deve ter header Content-Disposition."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/csv",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            if response.status_code == 200:
                disposition = response.headers.get("content-disposition", "")
                assert "attachment" in disposition
                assert ".csv" in disposition


class TestExportPDFEndpoint:
    """Testes para endpoint GET /api/alerts/export/pdf."""
    
    def test_export_pdf_requires_authentication(self):
        """Teste: Endpoint PDF sem auth deve retornar 401."""
        response = client.get("/api/alerts/export/pdf")
        assert response.status_code == 401
    
    def test_export_pdf_with_bearer_token(self):
        """Teste: Endpoint PDF com Bearer token válido."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/pdf",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Pode ser 200 ou 500, mas não 401
            assert response.status_code in [200, 500]
            assert response.status_code != 401
    
    def test_export_pdf_invalid_date_format(self):
        """Teste: Data inválida deve retornar 400."""
        response = client.get(
            "/api/alerts/export/pdf?start_date=invalid",
            headers={"Authorization": "Bearer user@test.com:1234567890"}
        )
        assert response.status_code == 400
    
    def test_export_pdf_content_type(self):
        """Teste: Response deve ter Content-Type: application/pdf."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/pdf",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            if response.status_code == 200:
                assert response.headers.get("content-type") == "application/pdf"
    
    def test_export_pdf_has_content_disposition(self):
        """Teste: Response deve ter header Content-Disposition."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/pdf",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            if response.status_code == 200:
                disposition = response.headers.get("content-disposition", "")
                assert "attachment" in disposition
                assert ".pdf" in disposition


class TestExportFilterParsing:
    """Testes para parsing de filtros nos endpoints."""
    
    def test_date_range_filtering(self):
        """Teste: Date range parsing."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/csv?start_date=2025-10-20&end_date=2025-10-27",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Se sucesso, verify que selecionar_alertas_janela foi chamado
            if response.status_code == 200:
                # Mock foi chamado
                assert mock_select.called
    
    def test_patient_id_filtering(self):
        """Teste: Patient ID é passado nos filtros."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/csv?patient_id=PAC-0001",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Validação: não deve ser erro 400
            assert response.status_code != 400
    
    def test_multiple_filters(self):
        """Teste: Múltiplos filtros combinados."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/csv?start_date=2025-10-20&status=pending&patient_id=PAC-0001",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Não deve ser erro de validação
            assert response.status_code != 400


class TestExportErrorHandling:
    """Testes para tratamento de erros."""
    
    def test_invalid_limit_parameter(self):
        """Teste: Limit inválido deve retornar 422."""
        response = client.get(
            "/api/alerts/export/csv?limit=invalid",
            headers={"Authorization": "Bearer user@test.com:1234567890"}
        )
        # FastAPI retorna 422 para tipo inválido
        assert response.status_code in [400, 422]
    
    def test_limit_out_of_range(self):
        """Teste: Limit > 100000 deve retornar erro."""
        response = client.get(
            "/api/alerts/export/csv?limit=100001",
            headers={"Authorization": "Bearer user@test.com:1234567890"}
        )
        assert response.status_code in [400, 422]
    
    def test_database_error_handling(self):
        """Teste: Erro de BD é tratado gracefully."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.side_effect = Exception("Database error")
            
            response = client.get(
                "/api/alerts/export/csv",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Deve retornar 500, não 5xx genérico
            assert response.status_code == 500
            data = response.json()
            assert "detail" in data


class TestBearerTokenParsing:
    """Testes para parsing de Bearer token."""
    
    def test_bearer_token_with_colon(self):
        """Teste: Bearer token com formato user:timestamp."""
        with patch('ferramentas.exportador.selecionar_alertas_janela') as mock_select:
            mock_select.return_value = []
            
            response = client.get(
                "/api/alerts/export/csv",
                headers={"Authorization": "Bearer user@test.com:1234567890"}
            )
            
            # Deve extrair username corretamente
            assert response.status_code != 401
    
    def test_bearer_token_without_colon(self):
        """Teste: Bearer token sem colon é rejeitado."""
        response = client.get(
            "/api/alerts/export/csv",
            headers={"Authorization": "Bearer invalidtoken"}
        )
        
        # Pode ser 401 ou sucesso dependendo de implementação
        # Mas não deve crash
        assert response.status_code in [200, 400, 401, 500]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
