"""Rede de segurança do C3: prova que o caminho de tempo dos alertas trata o
banco como UTC naive de forma consistente, independente do fuso do servidor.

Estes testes rodam iguais sob TZ=UTC e TZ=America/Sao_Paulo (o CI usa SP). Eles
falhariam com o código antigo, que usava datetime.now() local para a janela de
alertas e comparava timestamps UTC diretamente com as horas locais da agenda.
"""
import types
from datetime import datetime, timedelta, UTC

import pandas as pd

from interface.db_core import connect, criar_esquema, utc_now_iso
from interface.repositories.alertas import inserir_alertas, selecionar_alertas_janela
from interface.dao_agenda import criar_agenda, ensure_agendas_table
from interface.tempo import agora_utc_naive
from modulo_alerta.engine import processar_alertas


def _criar_paciente(db_path: str, paciente_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO pacientes(id) VALUES (?)", (paciente_id,))
        conn.commit()


def test_utc_now_iso_retorna_utc_e_nao_hora_local():
    """`utc_now_iso()` alimenta created_at/updated_at, paciente_cama_history e
    as janelas de device_assignments. Usava datetime.now() (LOCAL) apesar do
    nome: sob TZ=America/Sao_Paulo isso gravava tudo 3h atrás.

    Nota: sob TZ=UTC este teste passa com ou sem o bug (não há como distinguir).
    Ele protege o CI e o container, que rodam com TZ=America/Sao_Paulo.
    """
    esperado = datetime.now(UTC).replace(tzinfo=None)
    obtido = datetime.fromisoformat(utc_now_iso())

    assert abs((obtido - esperado).total_seconds()) < 5, (
        f"utc_now_iso() devolveu {obtido}, esperado ~{esperado} (UTC). "
        "Provavelmente voltou a usar datetime.now() local."
    )


def test_atribuicao_de_device_nao_comeca_no_passado(tmp_path):
    """Ao vincular um paciente a uma cama, o início da atribuição do device
    deve ser ~agora em UTC.

    Com a hora local, `start_ms` ficava 3h no passado e o
    `resolver_paciente_por_device_em` passava a atribuir a esse paciente as
    leituras das 3 horas ANTERIORES — quando ele ainda não estava no leito.
    """
    from interface.repositories.devices import registrar_device, resolver_paciente_por_device_em
    from interface.repositories.pacientes import PatientRepository

    db = str(tmp_path / "dados.db")
    criar_esquema(db)
    registrar_device(db, "ESP32-A")

    with connect(db) as conn:
        conn.execute(
            "INSERT INTO device_assignments (device_id, cama_id, paciente_id, start_ts, start_ms)"
            " VALUES (?, ?, ?, ?, ?)",
            ("ESP32-A", "101/A", "PAC-ANTIGO", "2020-01-01T00:00:00", 1577836800000),
        )
        conn.commit()

    repo = PatientRepository(db)
    repo.create(nome="Novo", perfil="medio", cama_id="101/A")

    agora_ms = int(datetime.now(UTC).timestamp() * 1000)
    # 30 min antes de vincular: o paciente novo ainda NÃO estava nesta cama.
    antes_ms = agora_ms - 30 * 60 * 1000

    with connect(db) as conn:
        row = conn.execute(
            "SELECT paciente_id FROM device_assignments WHERE device_id = ?"
            " AND end_ms IS NULL ORDER BY start_ms DESC LIMIT 1",
            ("ESP32-A",),
        ).fetchone()
    novo_pid = row["paciente_id"]

    assert resolver_paciente_por_device_em(db, "ESP32-A", agora_ms) == novo_pid
    assert resolver_paciente_por_device_em(db, "ESP32-A", antes_ms) != novo_pid, (
        "leitura de 30min atrás foi atribuída a um paciente que ainda não estava "
        "no leito — start_ms da atribuição está no passado (hora local?)"
    )


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
