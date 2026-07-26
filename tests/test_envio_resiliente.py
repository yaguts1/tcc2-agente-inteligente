"""A amostra de sensor nao pode ser perdida por uma falha temporaria.

Estes testes fixam a politica de entrega que o simulador de bancada
(`scripts/simulador_dispositivo.py`) e o firmware
(`firmware/esp32_replay/esp32_replay.ino`) implementam. O sketch C++ nao tem
como ser exercitado sem hardware, entao a regra e testada aqui — se um dia os
dois divergirem, e este arquivo que diz qual comportamento foi decidido.

O que estava errado antes:

- o simulador imprimia o erro e seguia para a proxima amostra: qualquer
  oscilacao de rede virava buraco no historico do paciente;
- o firmware desistia depois de 5 tentativas e parava o replay DE VEZ, exigindo
  um CMD_START manual que ninguem numa ala vai dar;
- e, ao desistir, gravava o checkpoint na posicao ja lida do arquivo, pulando
  para sempre justamente o evento que nao tinha sido entregue.
"""

import pytest

from scripts.envio_resiliente import (
    Contadores,
    PoliticaRetry,
    Resultado,
    classificar,
    entregar,
)


@pytest.mark.parametrize(
    "status,esperado",
    [
        (200, Resultado.ACK),
        (201, Resultado.ACK),
        (None, Resultado.TRANSIENTE),   # conexao caiu
        (500, Resultado.TRANSIENTE),
        (503, Resultado.TRANSIENTE),    # servidor reiniciando
        (408, Resultado.TRANSIENTE),
        (429, Resultado.TRANSIENTE),
        (401, Resultado.TRANSIENTE),    # token errado: erro de configuracao
        (403, Resultado.TRANSIENTE),
        (422, Resultado.PERMANENTE),    # payload que o servidor nunca aceita
        (404, Resultado.PERMANENTE),
    ],
)
def test_classificacao(status, esperado):
    assert classificar(status) is esperado


def _politica(**kw):
    # Sem jitter e com base minima: os testes verificam a POLITICA, nao o relogio.
    kw.setdefault("base_s", 0.01)
    kw.setdefault("jitter", False)
    return PoliticaRetry(**kw)


def test_insiste_ate_o_servidor_voltar():
    """Servidor fora do ar por varias tentativas: a amostra tem de chegar."""
    respostas = [None, 503, 503, 500, 200]
    contadores = Contadores()

    resultado = entregar(
        lambda: respostas.pop(0), _politica(), contadores, dormir=lambda _: None, registrar=lambda _: None
    )

    assert resultado is Resultado.ACK
    assert contadores.entregues == 1
    assert contadores.tentativas == 5
    assert respostas == []


def test_nao_desiste_por_padrao():
    """`tentativas_max=0` = infinito. Uma queda longa nao pode encerrar o envio.

    Antes eram 5 tentativas; com backoff de 500 ms dobrando, um reinicio de
    servidor de mais de ~16 s parava o dispositivo permanentemente.
    """
    falhas = 50
    chamadas = {"n": 0}

    def enviar():
        chamadas["n"] += 1
        return 200 if chamadas["n"] > falhas else 503

    contadores = Contadores()
    resultado = entregar(
        enviar, _politica(), contadores, dormir=lambda _: None, registrar=lambda _: None
    )

    assert resultado is Resultado.ACK
    assert chamadas["n"] == falhas + 1


def test_payload_recusado_nao_trava_a_fila():
    """422 nunca vai virar 200. Insistir bloquearia todas as amostras seguintes."""
    contadores = Contadores()

    resultado = entregar(
        lambda: 422, _politica(), contadores, dormir=lambda _: None, registrar=lambda _: None
    )

    assert resultado is Resultado.PERMANENTE
    assert contadores.tentativas == 1, "nao deve repetir um payload recusado em definitivo"
    assert contadores.descartados == 1, "o descarte precisa ser contado, nunca silencioso"


def test_limite_configurado_e_respeitado_sem_marcar_entrega():
    """Quem configurar um limite recebe TRANSIENTE — a amostra NAO foi entregue.

    O desfecho importa: e ele que diz a quem chamou para preservar a amostra em
    vez de avancar o ponto de retomada.
    """
    contadores = Contadores()

    resultado = entregar(
        lambda: 503,
        _politica(tentativas_max=3),
        contadores,
        dormir=lambda _: None,
        registrar=lambda _: None,
    )

    assert resultado is Resultado.TRANSIENTE
    assert contadores.tentativas == 3
    assert contadores.entregues == 0
    assert contadores.descartados == 0


def test_backoff_cresce_e_tem_teto():
    """Exponencial para nao martelar o servidor, com teto para nao dormir eternamente."""
    politica = PoliticaRetry(base_s=0.5, backoff_max_s=60.0, jitter=False)

    esperas = [politica.espera(i) for i in range(10)]

    assert esperas[:4] == [0.5, 1.0, 2.0, 4.0]
    assert esperas == sorted(esperas), "o backoff nao pode diminuir"
    assert max(esperas) == 60.0


def test_jitter_fica_dentro_da_faixa():
    """Jitter existe para dessincronizar N dispositivos, sem estourar o teto."""
    politica = PoliticaRetry(base_s=1.0, backoff_max_s=10.0, jitter=True)

    for _ in range(200):
        espera = politica.espera(3)  # base 8s, teto 10s
        assert 8.0 <= espera <= 10.0
