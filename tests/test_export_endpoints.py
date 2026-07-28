"""Testes de integração para os endpoints de exportação (CSV/PDF).

IMPORTANTE (segurança): estes endpoints exportam dados clínicos de pacientes.
A autenticação é feita via JWT (`get_current_user`). Este arquivo foi reescrito
para PROVAR que o bypass antigo — em que `Authorization: Bearer <user>:<qualquer>`
era aceito sem verificar o token — está FECHADO. Não reintroduzir asserções
tautológicas como `assert status in [200, 500]` nem tokens forjados como
credencial válida.
"""

import pytest
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from interface.api import router
from interface.auth_utils import create_access_token

# Criar app e registrar router
app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _auth_headers(username: str = "tester") -> dict:
    """Header Authorization com um JWT REAL (assinado pela mesma SECRET_KEY
    que `verify_token` usa).

    CRIA a linha em `users` tambem. Nao e detalhe de conveniencia: `sessao_valida`
    recusa token cujo `sub` nao exista no banco — senao um usuario REMOVIDO
    continuaria autenticado ate o token expirar.

    Antes este arquivo so assinava o token e dependia de outro teste, em outro
    arquivo, ter criado "tester" por acaso no mesmo banco. Passava por ordem de
    execucao: rodado isolado, os 16 testes davam 401, e qualquer arquivo novo
    que mudasse a ordem alfabetica quebrava todos de uma vez — sem que a causa
    tivesse relacao nenhuma com o que o arquivo testa (export e /auth/me).
    """
    from interface.api_shared import DB_PATH
    from interface.repositories.users import UserRepository

    try:
        UserRepository(DB_PATH).create(username, "hash-de-teste", role="admin")
    except Exception:
        pass  # ja existe, ou banco ainda sem a tabela — o token vale igual
    token = create_access_token({"sub": username, "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Segurança: o bypass de autenticação deve estar fechado
# ============================================================================

class TestExportAuthentication:
    """O contrato de segurança destes endpoints."""

    def test_csv_sem_credencial_retorna_401(self):
        response = client.get("/api/alerts/export/csv")
        assert response.status_code == 401

    def test_pdf_sem_credencial_retorna_401(self):
        response = client.get("/api/alerts/export/pdf")
        assert response.status_code == 401

    def test_csv_rejeita_token_forjado_com_colon(self):
        """Regressão do bypass: `Bearer <user>:<qualquer>` NÃO pode autenticar.
        Antes, o código fazia `token.split(':')[0]` e confiava no prefixo sem
        verificar assinatura — qualquer um baixava dados de paciente."""
        response = client.get(
            "/api/alerts/export/csv",
            headers={"Authorization": "Bearer admin:1234567890"},
        )
        assert response.status_code == 401

    def test_pdf_rejeita_token_forjado_com_colon(self):
        response = client.get(
            "/api/alerts/export/pdf",
            headers={"Authorization": "Bearer admin:1234567890"},
        )
        assert response.status_code == 401

    def test_csv_rejeita_token_arbitrario_sem_assinatura(self):
        response = client.get(
            "/api/alerts/export/csv",
            headers={"Authorization": "Bearer nao-e-um-jwt-valido"},
        )
        assert response.status_code == 401

    def test_csv_rejeita_cookie_session_user_forjado(self):
        """Cookie `session_user` em texto puro (forjável) não pode autenticar.
        Só JWT assinado (Bearer ou cookie access_token) é aceito."""
        c = TestClient(app)
        c.cookies.set("session_user", "admin")
        response = c.get("/api/alerts/export/csv")
        assert response.status_code == 401

    def test_csv_com_jwt_valido_passa_da_auth(self):
        """JWT válido autentica e o export roda (não é 401/403)."""
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get("/api/alerts/export/csv", headers=_auth_headers())
        assert response.status_code == 200

    def test_pdf_com_jwt_valido_passa_da_auth(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get("/api/alerts/export/pdf", headers=_auth_headers())
        assert response.status_code == 200


# ============================================================================
# CSV: conteúdo e cabeçalhos (sempre autenticado com JWT válido)
# ============================================================================

class TestExportCSVEndpoint:

    def test_csv_content_type(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get("/api/alerts/export/csv", headers=_auth_headers())
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    def test_csv_content_disposition(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get("/api/alerts/export/csv", headers=_auth_headers())
        assert response.status_code == 200
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".csv" in disposition

    def test_csv_exporta_dados(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = [
                {
                    "paciente_id": "PAC-0001",
                    "inicio": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    "fim": None,
                    "tipo": "imobilidade",
                    "perfil": "alto",
                    "janela_min": 60,
                    "status": "aberto",
                    "duracao_min": None,
                }
            ]
            response = client.get("/api/alerts/export/csv", headers=_auth_headers())
        assert response.status_code == 200
        assert "PAC-0001" in response.text


# ============================================================================
# PDF: conteúdo e cabeçalhos
# ============================================================================

class TestExportPDFEndpoint:

    def test_pdf_content_type(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get("/api/alerts/export/pdf", headers=_auth_headers())
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"

    def test_pdf_content_disposition(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get("/api/alerts/export/pdf", headers=_auth_headers())
        assert response.status_code == 200
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".pdf" in disposition


# ============================================================================
# Validação de filtros (autenticado)
# ============================================================================

class TestExportFilterValidation:

    def test_data_invalida_retorna_400(self):
        response = client.get(
            "/api/alerts/export/csv?start_date=invalid-date",
            headers=_auth_headers(),
        )
        assert response.status_code == 400
        assert "inválido" in response.json().get("detail", "").lower()

    def test_data_valida_nao_retorna_400(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get(
                "/api/alerts/export/csv?start_date=2025-10-20&end_date=2025-10-27",
                headers=_auth_headers(),
            )
        assert response.status_code == 200

    def test_status_invalido_retorna_400(self):
        response = client.get(
            "/api/alerts/export/csv?status=invalid_status",
            headers=_auth_headers(),
        )
        assert response.status_code == 400

    def test_statuses_validos_nao_retornam_400(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            for status_val in ["pending", "acknowledged", "completed"]:
                response = client.get(
                    f"/api/alerts/export/csv?status={status_val}",
                    headers=_auth_headers(),
                )
                assert response.status_code == 200, f"Status '{status_val}' deveria ser válido"

    def test_patient_id_filtra(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.return_value = []
            response = client.get(
                "/api/alerts/export/csv?patient_id=PAC-0001",
                headers=_auth_headers(),
            )
        assert response.status_code == 200

    def test_limit_tipo_invalido_retorna_422(self):
        response = client.get(
            "/api/alerts/export/csv?limit=invalid",
            headers=_auth_headers(),
        )
        assert response.status_code == 422

    def test_limit_fora_do_range_retorna_422(self):
        response = client.get(
            "/api/alerts/export/csv?limit=100001",
            headers=_auth_headers(),
        )
        assert response.status_code == 422


# ============================================================================
# Tratamento de erro
# ============================================================================

class TestExportErrorHandling:

    def test_erro_de_banco_retorna_500(self):
        with patch("ferramentas.exportador.selecionar_alertas_janela") as mock_select:
            mock_select.side_effect = Exception("Database error")
            response = client.get("/api/alerts/export/csv", headers=_auth_headers())
        assert response.status_code == 500
        assert "detail" in response.json()


class TestAuthMeHardening:
    """/auth/me só deve confiar em JWT, não no cookie session_user forjável."""

    def test_me_rejeita_cookie_session_user_forjado(self):
        c = TestClient(app)
        c.cookies.set("session_user", "admin")
        response = c.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_sem_credencial_retorna_401(self):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_com_jwt_valido_retorna_usuario(self):
        with patch("interface.routers.auth.user_repo.get_by_username", return_value=None):
            response = client.get("/api/auth/me", headers=_auth_headers("tester"))
        assert response.status_code == 200
        assert response.json().get("username") == "tester"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
