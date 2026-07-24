import pytest
from fastapi.testclient import TestClient
from interface.web import app
from interface.dao import inserir_alertas, selecionar_timeline, criar_usuario
from interface.auth_utils import create_access_token
from interface.api_shared import DB_PATH
import sqlite3

client = TestClient(app)

@pytest.fixture
def setup_db():
    # Create a test user
    try:
        criar_usuario(DB_PATH, "nurse_joy", "hashed_password", "Nurse Joy")
    except ValueError:
        pass # User might already exist
    
    # Create a test alert
    alert = {
        "paciente_id": "PAC-TEST-AUTH",
        "inicio": "2025-01-01T10:00:00",
        "fim": "2025-01-01T10:30:00",
        "tipo": "imobilidade",
        "perfil": "medio",
        "janela_min": 120,
        "status": "aberto",
        "duracao_min": 30
    }
    inserir_alertas(DB_PATH, [alert])
    
    yield
    
    # Cleanup
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM alertas WHERE paciente_id = 'PAC-TEST-AUTH'")
        conn.execute("DELETE FROM timeline_events WHERE paciente_id = 'PAC-TEST-AUTH'")
        conn.execute("DELETE FROM users WHERE username = 'nurse_joy'")

def test_acknowledge_requires_auth(setup_db):
    alert_id = "PAC-TEST-AUTH__2025-01-01T10:00:00"
    response = client.post(f"/api/frontend/alerts/{alert_id}/acknowledge")
    assert response.status_code == 401

def test_acknowledge_records_user(setup_db):
    alert_id = "PAC-TEST-AUTH__2025-01-01T10:00:00"
    
    # Generate token
    token = create_access_token({"sub": "nurse_joy"})
    
    response = client.post(
        f"/api/frontend/alerts/{alert_id}/acknowledge",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    
    # Verify timeline
    timeline = selecionar_timeline(DB_PATH, paciente_id="PAC-TEST-AUTH")
    ack_event = next((e for e in timeline if e["tipo"] == "alert_ack"), None)
    
    assert ack_event is not None
    assert "nurse_joy" in ack_event["descricao"]
    assert ack_event["meta"]["user"] == "nurse_joy"

def test_complete_records_user(setup_db):
    # Reset alert status first
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE alertas SET status = 'aberto' WHERE paciente_id = 'PAC-TEST-AUTH'")
        
    alert_id = "PAC-TEST-AUTH__2025-01-01T10:00:00"
    
    # Generate token
    token = create_access_token({"sub": "nurse_joy"})
    
    response = client.post(
        f"/api/frontend/alerts/{alert_id}/complete",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    
    # Verify timeline
    timeline = selecionar_timeline(DB_PATH, paciente_id="PAC-TEST-AUTH")
    close_event = next((e for e in timeline if e["tipo"] == "alert_close"), None)
    
    assert close_event is not None
    assert "nurse_joy" in close_event["descricao"]
    assert close_event["meta"]["user"] == "nurse_joy"
