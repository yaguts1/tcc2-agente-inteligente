"""Rede de segurança do C3: prova que o caminho de tempo dos alertas trata o
banco como UTC naive de forma consistente, independente do fuso do servidor.

Estes testes rodam iguais sob TZ=UTC e TZ=America/Sao_Paulo (o CI usa SP). Eles
falhariam com o código antigo, que usava datetime.now() local para a janela de
alertas e comparava timestamps UTC diretamente com as horas locais da agenda.
"""
import types
from datetime import datetime, timedelta

import pandas as pd
import pytest

from interface.db_core import connect, criar_esquema
from interface.repositories.alertas import inserir_alertas, selecionar_alertas_janela
from interface.dao_agenda import criar_agenda, ensure_agendas_table
from interface.tempo import agora_utc_naive
from modulo_alerta.engine import processar_alertas


def _criar_paciente(db_path: str, paciente_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (paciente_id,))
        conn.commit()


def test_janela_de_alertas_usa_agora_em_utc(tmp_path):
    """Um alerta com `inicio` = agora-UTC deve aparecer numa janela estreita
    (1h). Com now() local, a janela ficaria deslocada pelo offset do fuso e o
    alerta recente cairia fora dela."""
    db = str(tmp_path / "dados.db")
    criar_esquema(db)

    inicio = agora_utc_naive().strftime("%Y-%m-%dT%H:%M:%S")
    inserir_alertas(db, [{
        "paciente_id": "PAC-1", "inicio": inicio, "tipo": "imobilidade",
        "perfil": "alto", "janela_min": 60, "status": "aberto",
    }])

    res = selecionar_alertas_janela(db, horas=1)
    assert any(a["paciente_id"] == "PAC-1" for a in res), \
        "alerta recente (UTC) deveria estar na janela de 1h"


def test_supressao_casa_hora_local_com_alerta_utc(tmp_path, monkeypatch):
    """Alerta cujo `inicio` é 15:00 UTC (= 12:00 America/Sao_Paulo) deve ser
    SUPRIMIDO por uma agenda de almoço definida em horário LOCAL 11:00-13:00.
    Com o código antigo (compara 15:00 UTC direto contra 11:00-13:00) o alerta
    NÃO seria suprimido."""
    db = str(tmp_path / "dados.db")
    criar_esquema(db)
    ensure_agendas_table(db)
    monkeypatch.setattr("modulo_alerta.engine.config", types.SimpleNamespace(db_path=db))

    paciente_id = "PAC-SUP"
    _criar_paciente(db, paciente_id)

    # 2025-06-16 é segunda-feira. Agenda de almoço em horário LOCAL (SP).
    dia = datetime(2025, 6, 16)
    criar_agenda(
        paciente_id=paciente_id, tipo="refeicao", modo="suprimir",
        hora_inicio="11:00", hora_fim="13:00", dias_semana=[dia.weekday()],
        data_inicio=dia.date().isoformat(), data_fim=None,
        reducao_janela_min=None, descricao="Almoço (local)", db_path=db,
    )

    # Imobilidade em UTC terminando ~15:00 UTC (= 12:00 SP) → alerta inicio 15:00 UTC.
    base_utc = datetime(2025, 6, 16, 14, 0, 0)
    ts = [base_utc + timedelta(minutes=i) for i in range(70)]
    df = pd.DataFrame({"timestamp": ts, "postura": ["supino"] * 70})

    _, alertas = processar_alertas(df_grade=df, perfil="alto", paciente_id=paciente_id)

    # O alerta cai às 15:00 UTC = 12:00 SP, dentro do almoço local → suprimido.
    assert alertas == [], f"esperava supressão (12:00 local), veio: {alertas}"


def test_supressao_nao_afeta_alerta_fora_do_almoco_local(tmp_path, monkeypatch):
    """Controle: alerta às 20:00 UTC (= 17:00 SP) NÃO deve ser suprimido pela
    agenda de almoço local 11:00-13:00."""
    db = str(tmp_path / "dados.db")
    criar_esquema(db)
    ensure_agendas_table(db)
    monkeypatch.setattr("modulo_alerta.engine.config", types.SimpleNamespace(db_path=db))

    paciente_id = "PAC-SUP2"
    _criar_paciente(db, paciente_id)

    dia = datetime(2025, 6, 16)
    criar_agenda(
        paciente_id=paciente_id, tipo="refeicao", modo="suprimir",
        hora_inicio="11:00", hora_fim="13:00", dias_semana=[dia.weekday()],
        data_inicio=dia.date().isoformat(), data_fim=None,
        reducao_janela_min=None, descricao="Almoço (local)", db_path=db,
    )

    base_utc = datetime(2025, 6, 16, 19, 0, 0)  # alerta ~20:00 UTC = 17:00 SP
    ts = [base_utc + timedelta(minutes=i) for i in range(70)]
    df = pd.DataFrame({"timestamp": ts, "postura": ["supino"] * 70})

    _, alertas = processar_alertas(df_grade=df, perfil="alto", paciente_id=paciente_id)

    assert alertas, "17:00 local está fora do almoço; alerta não deveria ser suprimido"
