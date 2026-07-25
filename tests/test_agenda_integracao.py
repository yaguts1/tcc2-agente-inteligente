"""Integration tests for agenda system with alert suppression."""

import os
import sqlite3
import tempfile
import types
from datetime import datetime, timedelta

import pytest
import pandas as pd

from interface.dao_agenda import (
    criar_agenda,
    is_timestamp_in_suppressed_period,
    ensure_agendas_table,
)
from interface.dao import _connect
from modulo_alerta.engine import processar_alertas


@pytest.fixture
def db_temp():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Initialize database schema. `_connect` agora e um context manager que
    # commita e FECHA ao sair (antes devolvia a Connection crua e o close ficava
    # por conta de quem chamasse).
    with _connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pacientes (
                id TEXT PRIMARY KEY
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paciente_fichas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id TEXT UNIQUE,
                nome TEXT,
                perfil TEXT,
                cama_id TEXT,
                observacoes TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(paciente_id) REFERENCES pacientes(id)
            )
        """)

    yield path
    
    # Cleanup - force close any remaining connections
    # Close any open connections
    try:
        sqlite3.connect(path).close()
    except Exception:
        pass
    
    # Try to remove file, with retry for Windows
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if os.path.exists(path):
                os.unlink(path)
            break
        except PermissionError:
            if attempt < max_retries - 1:
                import time
                time.sleep(0.1)
            else:
                pass  # Silently ignore if can't delete


def _create_test_patient(paciente_id: str, db_path: str):
    """Helper to create a test patient."""
    with _connect(db_path) as conn:
        conn.execute("INSERT INTO pacientes (id) VALUES (?)", (paciente_id,))
        conn.execute(
            """INSERT INTO paciente_fichas (paciente_id, nome, perfil, cama_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (paciente_id, "Test Patient", "medio", "101", datetime.now().isoformat(), datetime.now().isoformat())
        )


def test_agenda_suppression_basic(db_temp):
    """Test that alerts are suppressed during scheduled periods."""
    paciente_id = "PAC-TEST-001"
    
    # Create patient
    _create_test_patient(paciente_id, db_temp)
    
    # Ensure agenda table exists
    ensure_agendas_table(db_path=db_temp)
    
    # Create a suppression agenda for meals: 12:00-13:00
    now = datetime.now()
    agenda_inicio = now.replace(hour=12, minute=0, second=0, microsecond=0)
    
    criar_agenda(
        paciente_id=paciente_id,
        tipo="refeicao",
        modo="suprimir",
        hora_inicio="12:00",
        hora_fim="13:00",
        dias_semana=[now.weekday()],  # Today
        data_inicio=now.date().isoformat(),
        data_fim=None,
        reducao_janela_min=None,
        descricao="Almoço - suprimir alertas",
        db_path=db_temp,
    )
    
    # Test 1: Timestamp DURING suppression period should be suppressed
    timestamp_durante = agenda_inicio.isoformat()
    is_sup, modo = is_timestamp_in_suppressed_period(
        db_path=db_temp,
        paciente_id=paciente_id,
        timestamp=timestamp_durante,
    )
    assert is_sup is True
    assert modo == "suprimir"
    
    # Test 2: Timestamp OUTSIDE suppression period should NOT be suppressed
    timestamp_fora = now.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
    is_sup, modo = is_timestamp_in_suppressed_period(
        db_path=db_temp,
        paciente_id=paciente_id,
        timestamp=timestamp_fora,
    )
    assert is_sup is False
    assert modo is None


def test_agenda_reduction(db_temp):
    """Test that alert windows are reduced during specified periods."""
    paciente_id = "PAC-TEST-002"
    
    # Create patient
    _create_test_patient(paciente_id, db_temp)
    
    # Ensure agenda table exists
    ensure_agendas_table(db_path=db_temp)
    
    # Create a reduction agenda for surgery: 09:00-11:00
    now = datetime.now()
    
    criar_agenda(
        paciente_id=paciente_id,
        tipo="cirurgia",
        modo="reduzir",
        hora_inicio="09:00",
        hora_fim="11:00",
        dias_semana=[now.weekday()],  # Today
        data_inicio=now.date().isoformat(),
        data_fim=None,
        reducao_janela_min=10,  # Reduce by 10 minutes
        descricao="Cirurgia - reduzir alertas",
        db_path=db_temp,
    )
    
    # Test: Timestamp DURING reduction period should return "reduzir" mode
    timestamp_durante = now.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()
    is_sup, modo = is_timestamp_in_suppressed_period(
        db_path=db_temp,
        paciente_id=paciente_id,
        timestamp=timestamp_durante,
    )
    assert is_sup is True
    assert modo == "reduzir"


def test_alert_engine_with_suppression(db_temp):
    """Test that alert engine applies suppression correctly."""
    paciente_id = "PAC-TEST-003"
    
    # Create patient
    _create_test_patient(paciente_id, db_temp)
    
    # Ensure agenda table exists
    ensure_agendas_table(db_path=db_temp)
    
    # Create suppression agenda for next hour
    now = datetime.now()
    hour_from_now = now + timedelta(hours=1)
    
    criar_agenda(
        paciente_id=paciente_id,
        tipo="refeicao",
        modo="suprimir",
        hora_inicio=hour_from_now.strftime("%H:%M"),
        hora_fim=(hour_from_now + timedelta(hours=1)).strftime("%H:%M"),
        dias_semana=[hour_from_now.weekday()],
        data_inicio=hour_from_now.date().isoformat(),
        data_fim=None,
        reducao_janela_min=None,
        descricao="Test suppression",
        db_path=db_temp,
    )
    
    # Create mock grade with incrementing timestamps:
    # 1. Series BEFORE suppression period (should generate alert)
    # 2. Series DURING suppression period (should be suppressed)
    
    timestamps_before = [now.replace(minute=i, second=0, microsecond=0) for i in range(20)]
    timestamps_during = [hour_from_now.replace(minute=i, second=0, microsecond=0) for i in range(20)]
    
    all_timestamps = timestamps_before + timestamps_during
    
    df_grade = pd.DataFrame({
        "timestamp": all_timestamps,
        "postura": ["deitado"] * 40,
    })
    
    # Process alerts (this should suppress the during alert)
    df_norm, alertas = processar_alertas(
        df_grade=df_grade,
        perfil="medio",
        paciente_id=paciente_id,
    )
    
    # We should have generated some alerts from the first period
    # and suppressed alerts from the second period
    print(f"Generated {len(alertas)} alerts")
    for alerta in alertas:
        print(f"  - {alerta}")


def test_multiple_agenda_modes(db_temp):
    """Test mode precedence: suprimir > reduzir > monitorar."""
    paciente_id = "PAC-TEST-004"
    
    # Create patient
    _create_test_patient(paciente_id, db_temp)
    
    # Ensure agenda table exists
    ensure_agendas_table(db_path=db_temp)
    
    now = datetime.now()
    
    # Create three overlapping agendas with different modes
    criar_agenda(
        paciente_id=paciente_id,
        tipo="procedimento",
        modo="monitorar",
        hora_inicio="10:00",
        hora_fim="12:00",
        dias_semana=[now.weekday()],
        data_inicio=now.date().isoformat(),
        data_fim=None,
        reducao_janela_min=None,
        descricao="Monitor only",
        db_path=db_temp,
    )
    
    criar_agenda(
        paciente_id=paciente_id,
        tipo="procedimento",
        modo="reduzir",
        hora_inicio="10:00",
        hora_fim="12:00",
        dias_semana=[now.weekday()],
        data_inicio=now.date().isoformat(),
        data_fim=None,
        reducao_janela_min=5,
        descricao="Reduce window",
        db_path=db_temp,
    )
    
    criar_agenda(
        paciente_id=paciente_id,
        tipo="procedimento",
        modo="suprimir",
        hora_inicio="10:00",
        hora_fim="12:00",
        dias_semana=[now.weekday()],
        data_inicio=now.date().isoformat(),
        data_fim=None,
        reducao_janela_min=None,
        descricao="Suppress all",
        db_path=db_temp,
    )
    
    # Test at 11:00 - should return SUPPRESS (highest priority)
    timestamp = now.replace(hour=11, minute=0, second=0, microsecond=0).isoformat()
    is_sup, modo = is_timestamp_in_suppressed_period(
        db_path=db_temp,
        paciente_id=paciente_id,
        timestamp=timestamp,
    )
    assert is_sup is True
    assert modo == "suprimir"  # Suprimir takes precedence


def test_engine_aplica_reducao_de_janela(db_temp, monkeypatch):
    """Regressão C1: uma agenda modo='reduzir' ativa no horário do alerta deve
    REDUZIR o `janela_min` do alerta gerado.

    Antes, o motor consultava `agendas_paciente ... AND deletado = 0` — coluna
    inexistente — e o erro era engolido por um `except: return 0`, então a
    redução NUNCA acontecia. Este teste falharia com o código antigo.
    """
    from configuracao import config as app_config

    # O motor lê agendas do config.db_path global (default "dados.db"); aponta
    # ele para o banco temporário deste teste.
    monkeypatch.setattr("modulo_alerta.engine.config", types.SimpleNamespace(db_path=db_temp))

    paciente_id = "PAC-TEST-REDUCAO"
    _create_test_patient(paciente_id, db_temp)
    ensure_agendas_table(db_path=db_temp)

    ref = datetime(2025, 6, 16, 10, 0, 0)  # segunda-feira
    reducao_min = 10

    criar_agenda(
        paciente_id=paciente_id,
        tipo="cirurgia",
        modo="reduzir",
        hora_inicio="00:00",
        hora_fim="23:59",
        dias_semana=[ref.weekday()],
        data_inicio=ref.date().isoformat(),
        data_fim=None,
        reducao_janela_min=reducao_min,
        descricao="Cirurgia - reduzir janela",
        db_path=db_temp,
    )

    # 70 min de imobilidade contínua (perfil 'alto' = janela 60 min) → gera alerta
    timestamps = [ref + timedelta(minutes=i) for i in range(70)]
    df_grade = pd.DataFrame({"timestamp": timestamps, "postura": ["supino"] * len(timestamps)})

    _, alertas = processar_alertas(df_grade=df_grade, perfil="alto", paciente_id=paciente_id)

    assert alertas, "esperava ao menos um alerta gerado"
    reduzidos = [a for a in alertas if a.get("modo_supressao") == "reduzido"]
    assert reduzidos, "esperava ao menos um alerta com redução aplicada (feature estava morta)"

    esperado = max(5, app_config.janela_por_perfil["alto"] - reducao_min)
    for a in reduzidos:
        assert a["janela_min"] == esperado


def test_engine_nao_reduz_fora_do_horario_da_agenda(db_temp, monkeypatch):
    """A redução só vale quando a agenda 'reduzir' casa com o horário/data do
    alerta. Uma agenda em outro dia da semana não deve reduzir nada."""
    monkeypatch.setattr("modulo_alerta.engine.config", types.SimpleNamespace(db_path=db_temp))

    paciente_id = "PAC-TEST-REDUCAO-FORA"
    _create_test_patient(paciente_id, db_temp)
    ensure_agendas_table(db_path=db_temp)

    ref = datetime(2025, 6, 16, 10, 0, 0)  # segunda-feira
    outro_dia = (ref.weekday() + 1) % 7  # dia da semana diferente

    criar_agenda(
        paciente_id=paciente_id,
        tipo="cirurgia",
        modo="reduzir",
        hora_inicio="00:00",
        hora_fim="23:59",
        dias_semana=[outro_dia],  # não casa com a data do alerta
        data_inicio=ref.date().isoformat(),
        data_fim=None,
        reducao_janela_min=10,
        descricao="Reduzir em outro dia",
        db_path=db_temp,
    )

    timestamps = [ref + timedelta(minutes=i) for i in range(70)]
    df_grade = pd.DataFrame({"timestamp": timestamps, "postura": ["supino"] * len(timestamps)})

    _, alertas = processar_alertas(df_grade=df_grade, perfil="alto", paciente_id=paciente_id)

    assert alertas, "esperava ao menos um alerta gerado"
    assert all(a.get("modo_supressao") != "reduzido" for a in alertas)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
