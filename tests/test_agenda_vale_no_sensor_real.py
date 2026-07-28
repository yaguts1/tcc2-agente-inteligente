"""A agenda de supressao funcionava na demo e nao funcionava em producao.

`modulo_alerta/engine.py` aplica supressao — e so e chamado pelo endpoint de
SIMULACAO (`routers/pacientes.py:266`), pelo CLI (`main.py:48`) e por um script
de demo. O caminho do sensor real e outro:

    POST /api/eventos -> ingestao_service.registrar_evento
                      -> PROCESSADOR.processar_amostra
                      -> nucleo/decisor.py

e esse caminho nunca importou `interface.dao_agenda`. A enfermagem cadastrava
"cirurgia 08:00-12:00, suprimir", via a agenda listada na tela, e o ESP32
alertava a cirurgia inteira.

E a classe de falha contra a qual `endpoints_agenda.py:50-54` ja avisava — "a
agenda ficava cadastrada, visivel na tela e sem efeito nenhum" — reintroduzida
numa camada diferente. Por isso estes testes entram pelo PROCESSADOR, nunca pelo
engine: um teste que passe pelo engine nao prova nada sobre producao.
"""

from datetime import datetime, timedelta

import pytest

from interface.dao_agenda import criar_agenda, ensure_agendas_table
from interface.db_core import connect, criar_esquema
from interface.tempo import utc_naive_para_local
from servicos.processamento_incremental import ProcessadorIncremental

PACIENTE = "PAC-0001"
PERFIL = "alto"          # janela de 60 min
JANELA_MIN = 60


@pytest.fixture
def db(tmp_path):
    caminho = str(tmp_path / "t.db")
    criar_esquema(caminho)
    ensure_agendas_table(caminho)
    with connect(caminho) as conn:
        conn.execute("INSERT INTO pacientes(id) VALUES (?)", (PACIENTE,))
    return caminho


@pytest.fixture
def processador(db):
    return ProcessadorIncremental(
        db_path=db,
        estrategia="estado_em_memoria",
        resolver_perfil=lambda _pid: PERFIL,
    )


def _base_utc_para_hora_local(hora_local: int) -> datetime:
    """Um instante UTC naive cuja hora LOCAL e a pedida.

    A agenda guarda horario local (o que a enfermagem digita) e o banco guarda
    UTC naive. Descobrir o offset medindo, em vez de assumir -3, mantem o teste
    valido em horario de verao e em CI com outro TZ.
    """
    referencia = datetime(2026, 3, 10, 12, 0, 0)
    offset_h = round((utc_naive_para_local(referencia) - referencia).total_seconds() / 3600)
    return referencia.replace(hour=(hora_local - offset_h) % 24, minute=0, second=0)


def _amostras(inicio: datetime, minutos: int, postura: str = "supino"):
    """Uma amostra por minuto, sempre a MESMA postura: imobilidade pura."""
    for i in range(minutos):
        yield {
            "paciente_id": PACIENTE,
            "postura": postura,
            "confianca": 0.95,
            "ts_utc": (inicio + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S"),
        }


def test_sem_agenda_o_alerta_acontece(processador):
    """Ancora: sem supressao, imobilidade alem da janela alerta. Se este falhar,
    os outros nao provam nada — estariam passando por falta de alerta nenhum."""
    inicio = _base_utc_para_hora_local(8)

    alertas = processador.processar_lote(_amostras(inicio, JANELA_MIN + 5))

    assert alertas, "cenario de controle nao gerou alerta"


def test_agenda_suprimir_silencia_o_caminho_do_sensor(db, processador):
    """O caso que estava quebrado."""
    criar_agenda(
        db, paciente_id=PACIENTE, tipo="cirurgia",
        hora_inicio="08:00", hora_fim="12:00", modo="suprimir",
        dias_semana=[0, 1, 2, 3, 4, 5, 6],
    )
    inicio = _base_utc_para_hora_local(8)

    alertas = processador.processar_lote(_amostras(inicio, JANELA_MIN + 5))

    assert alertas == [], "o ESP32 alertou durante a cirurgia agendada"


def test_supressao_nao_deixa_alerta_fantasma_no_estado(db, processador):
    """Suprimir DEPOIS de o decisor decidir deixaria `alerta_atual` preenchido.

    Um `alerta_atual` que ninguem viu bloqueia TODOS os alertas seguintes do
    paciente ate uma mudanca real de postura — o pior desfecho possivel, porque
    a tela fica verde enquanto o paciente segue imovel. Por isso a checagem e
    antes do decisor.
    """
    criar_agenda(
        db, paciente_id=PACIENTE, tipo="cirurgia",
        hora_inicio="08:00", hora_fim="12:00", modo="suprimir",
        dias_semana=[0, 1, 2, 3, 4, 5, 6],
    )
    inicio = _base_utc_para_hora_local(8)
    processador.processar_lote(_amostras(inicio, JANELA_MIN + 5))

    estado = processador._estado_cache.get(PACIENTE)
    assert estado is None or estado.alerta_atual is None, (
        "ficou um alerta aberto no estado que a tela nunca vai mostrar"
    )


def test_ao_sair_da_janela_a_corrida_recomeca(db, processador):
    """O periodo suprimido nao foi observado: nao pode contar como imobilidade.

    Somar as duas pontas como corrida continua acusaria imovel justamente o
    intervalo da cirurgia — quando o paciente estava sendo movido.
    """
    criar_agenda(
        db, paciente_id=PACIENTE, tipo="cirurgia",
        hora_inicio="08:00", hora_fim="12:00", modo="suprimir",
        dias_semana=[0, 1, 2, 3, 4, 5, 6],
    )
    inicio_suprimido = _base_utc_para_hora_local(8)

    # 4h dentro da janela, e depois 30 min fora dela (menos que a janela de 60).
    processador.processar_lote(_amostras(inicio_suprimido, 4 * 60))
    alertas = processador.processar_lote(
        _amostras(inicio_suprimido + timedelta(hours=4, minutes=1), 30)
    )

    assert alertas == [], (
        "as 4h suprimidas foram somadas aos 30 min seguintes e viraram alerta"
    )


def test_fora_do_horario_da_agenda_o_alerta_volta(db, processador):
    """Supressao e por JANELA, nao por paciente."""
    criar_agenda(
        db, paciente_id=PACIENTE, tipo="cirurgia",
        hora_inicio="08:00", hora_fim="12:00", modo="suprimir",
        dias_semana=[0, 1, 2, 3, 4, 5, 6],
    )
    inicio = _base_utc_para_hora_local(14)

    alertas = processador.processar_lote(_amostras(inicio, JANELA_MIN + 5))

    assert alertas, "a agenda das 08:00-12:00 silenciou as 14:00"


def test_agenda_de_outro_paciente_nao_silencia_este(db, processador):
    """Supressao e por PACIENTE, nao global."""
    with connect(db) as conn:
        conn.execute("INSERT INTO pacientes(id) VALUES ('PAC-0002')")
    criar_agenda(
        db, paciente_id="PAC-0002", tipo="cirurgia",
        hora_inicio="08:00", hora_fim="12:00", modo="suprimir",
        dias_semana=[0, 1, 2, 3, 4, 5, 6],
    )
    inicio = _base_utc_para_hora_local(8)

    alertas = processador.processar_lote(_amostras(inicio, JANELA_MIN + 5))

    assert alertas, "a cirurgia do vizinho de quarto silenciou este paciente"
