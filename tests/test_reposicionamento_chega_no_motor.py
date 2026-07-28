"""Clicar "Reposicionar" na tela nao contava para o motor.

`alterar_status_alerta` escrevia a linha em `alertas` e mais nada — a unica
chamada que tocava o PROCESSADOR era `interface/api.py:111`, marcada como uso de
teste.

Mas `nucleo/decisor.py:172` so abre alerta novo quando `alerta_atual is None`, e
`alerta_atual` so limpava sozinho com postura DIFERENTE sustentada por
`histerese_min` minutos. Entao, quando o paciente NAO foi virado de fato (ou o
sensor nao viu a mudanca):

    linha vira 'fechado'  ->  dashboard verde  ->  alerta_atual continua setado
                          ->  nenhum alerta novo, nunca mais

O paciente podia passar horas sobre o sacro atras de uma tela afirmando que
estava tudo em dia. E o inverso do modo de falha que
`repositories/monitoramento.py` ja cobre: la o sistema fica calado, aqui ele
afirma bem-estar.
"""

from datetime import datetime, timedelta

import pytest

from interface.db_core import connect, criar_esquema
from servicos.processamento_incremental import ProcessadorIncremental

PACIENTE = "PAC-0001"
JANELA_MIN = 60  # perfil alto
T0 = datetime(2026, 3, 10, 8, 0, 0)


@pytest.fixture
def db(tmp_path):
    caminho = str(tmp_path / "t.db")
    criar_esquema(caminho)
    with connect(caminho) as conn:
        conn.execute("INSERT INTO pacientes(id) VALUES (?)", (PACIENTE,))
    return caminho


@pytest.fixture
def processador(db):
    return ProcessadorIncremental(
        db_path=db,
        estrategia="estado_em_memoria",
        resolver_perfil=lambda _pid: "alto",
    )


def _imovel(inicio: datetime, minutos: int, postura: str = "supino"):
    for i in range(minutos):
        yield {
            "paciente_id": PACIENTE,
            "postura": postura,
            "confianca": 0.95,
            "ts_utc": (inicio + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S"),
        }


def test_sem_aviso_ao_motor_o_paciente_fica_sem_alerta_para_sempre(processador):
    """Documenta o mecanismo do defeito, para ninguem o reintroduzir.

    Fecha o alerta SO no banco (o que a tela fazia) e mostra que o motor segue
    achando que ha alerta aberto — logo, nao emite nenhum outro.
    """
    alertas = processador.processar_lote(_imovel(T0, JANELA_MIN + 5))
    assert alertas, "cenario de controle nao abriu alerta"

    # A tela fechou a linha no banco; o motor nao foi avisado.
    estado = processador._estado_cache[PACIENTE]
    assert estado.alerta_atual is not None

    # Paciente segue imovel por mais 3 horas na MESMA postura.
    seguintes = processador.processar_lote(
        _imovel(T0 + timedelta(minutes=JANELA_MIN + 6), 180)
    )
    assert seguintes == [], (
        "premissa mudou: sem aviso ao motor deveria continuar sem alerta novo"
    )


def test_apos_marcar_reposicionado_um_novo_alerta_nasce(processador):
    """A correcao: o motor sabe do reposicionamento e volta a vigiar."""
    processador.processar_lote(_imovel(T0, JANELA_MIN + 5))

    assert processador.marcar_reposicionado(PACIENTE) is True

    estado = processador._estado_cache[PACIENTE]
    assert estado.alerta_atual is None, "o alerta fantasma continuou no estado"

    # Paciente volta a ficar imovel: precisa alertar de novo.
    depois = T0 + timedelta(minutes=JANELA_MIN + 6)
    novos = processador.processar_lote(_imovel(depois, JANELA_MIN + 5))

    assert novos, "o paciente ficou imovel de novo e nenhum alerta nasceu"


def test_a_janela_recomeca_no_reposicionamento(processador):
    """Reiniciar a corrida e o ponto, nao so limpar o alerta.

    O relogio da proxima janela tem que comecar quando o paciente foi virado —
    se a corrida antiga sobrevivesse, o alerta seguinte sairia imediatamente,
    reclamando de imobilidade que ja tinha sido resolvida.
    """
    processador.processar_lote(_imovel(T0, JANELA_MIN + 5))
    processador.marcar_reposicionado(PACIENTE)

    depois = T0 + timedelta(minutes=JANELA_MIN + 6)
    # Menos que a janela: ainda nao pode alertar.
    cedo_demais = processador.processar_lote(_imovel(depois, JANELA_MIN - 10))

    assert cedo_demais == [], (
        "alertou antes de a janela completa correr desde o reposicionamento"
    )


def test_paciente_desconhecido_do_motor_nao_quebra(processador):
    """A tela pode fechar alerta de paciente cujo estado o motor nao tem
    (reinicio de processo, alerta importado). Precisa ser no-op, nao excecao."""
    assert processador.marcar_reposicionado("PAC-INEXISTENTE") is False
