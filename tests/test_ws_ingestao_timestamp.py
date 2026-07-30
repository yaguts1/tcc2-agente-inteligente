"""A amostra vale pelo instante em que foi MEDIDA, nao pelo em que chegou.

O firmware agora repete indefinidamente enquanto a falha for temporaria, entao
uma amostra pode chegar horas depois de medida — foi para isso que o buffer foi
corrigido. Isso torna a distincao entre "medido as 02:00" e "recebido as 06:00"
uma diferenca real, nao teorica.

No WebSocket de ingestao, quando a validacao do payload falhava, o evento orfao
era gravado com `datetime.now()`. Isso desfazia a correcao da reconciliacao,
que resolve o dono da leitura pelo `ts_ms` do evento: uma amostra medida as
02:00 e recebida as 06:00 seria atribuida a quem ocupava o leito as 06:00 —
exatamente o defeito que a resolucao por tempo eliminou.
"""

from datetime import datetime, timedelta, UTC

from interface.routers.ingestao import _ts_da_medicao


def test_usa_o_ts_do_payload_e_nao_a_hora_atual():
    medido = "2026-07-26T02:00:00"

    resultado = _ts_da_medicao({"ts_utc": medido}, "dev-1")

    assert resultado == datetime(2026, 7, 26, 2, 0, 0)
    assert resultado.tzinfo is None, "o banco guarda UTC naive"


def test_converte_para_utc_quando_vem_com_offset():
    """Firmware que manda offset nao pode deslocar a linha do tempo."""
    resultado = _ts_da_medicao({"ts_utc": "2026-07-26T02:00:00-03:00"}, "dev-1")

    assert resultado == datetime(2026, 7, 26, 5, 0, 0)


def test_aceita_sufixo_z():
    resultado = _ts_da_medicao({"ts_utc": "2026-07-26T02:00:00Z"}, "dev-1")

    assert resultado == datetime(2026, 7, 26, 2, 0, 0)


def test_sem_ts_cai_na_hora_atual():
    """Descartar seria pior; o default fica, mas e o ultimo recurso."""
    antes = datetime.now(UTC).replace(tzinfo=None)

    resultado = _ts_da_medicao({}, "dev-1")

    assert resultado >= antes - timedelta(seconds=2)
    assert resultado.tzinfo is None


def test_ts_ilegivel_cai_na_hora_atual_sem_estourar():
    antes = datetime.now(UTC).replace(tzinfo=None)

    resultado = _ts_da_medicao({"ts_utc": "ontem de manha"}, "dev-1")

    assert resultado >= antes - timedelta(seconds=2)


def test_amostra_atrasada_preserva_o_instante_da_medicao():
    """O caso que o buffer do firmware tornou comum.

    Se o instante fosse o da chegada, a reconciliacao atribuiria a leitura ao
    ocupante atual do leito — o paciente errado.
    """
    medido = datetime(2026, 7, 26, 2, 0, 0)

    resultado = _ts_da_medicao({"ts_utc": medido.strftime("%Y-%m-%dT%H:%M:%S")}, "dev-1")

    agora = datetime.now(UTC).replace(tzinfo=None)
    assert resultado == medido
    assert abs((agora - resultado).total_seconds()) > 60, (
        "o teste so tem valor se a medicao for claramente anterior a execucao"
    )
