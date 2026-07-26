"""A supressao por agenda precisa realmente suprimir.

Uma agenda de supressao e uma promessa clinica: "nao me alerte agora, eu sei o
que esta acontecendo com este paciente". Ela falha em dois sentidos opostos e
os dois sao ruins — deixar de suprimir gera alarme durante um procedimento
(fadiga de alarme, o alerta seguinte e ignorado); suprimir demais esconde um
paciente que precisa ser virado.

O defeito encontrado era do primeiro tipo, no pior formato possivel: a janela
que cruza a meia-noite (22:00-06:00, "nao perturbar durante o sono") era aceita
pela API, aparecia na tela como configurada e nunca suprimia coisa alguma,
porque o casamento era `inicio <= ts <= fim` — sempre falso quando fim < inicio.
"""

from datetime import datetime

import pytest

from interface.dao_agenda import _timestamp_matches_agenda


def _agenda(hora_inicio, hora_fim, *, dias=None, modo="suprimir"):
    return {
        "hora_inicio": hora_inicio,
        "hora_fim": hora_fim,
        "modo": modo,
        "dias_semana": dias if dias is not None else [0, 1, 2, 3, 4, 5, 6],
        "data_inicio": None,
        "data_fim": None,
        "reducao_janela_min": 0,
    }


def _em(dia, hora):
    h, m = hora.split(":")
    return datetime(2026, 1, dia, int(h), int(m))


# 2026-01-05 e uma SEGUNDA (weekday 0); 06 terca; 04 domingo (weekday 6).


@pytest.mark.parametrize(
    "hora,esperado",
    [("11:30", False), ("12:00", True), ("12:30", True), ("13:00", True), ("13:30", False)],
)
def test_janela_diurna(hora, esperado):
    """Caso simples, que ja funcionava — fica como guarda contra regressao."""
    assert _timestamp_matches_agenda(_em(5, hora), _agenda("12:00", "13:00")) is esperado


@pytest.mark.parametrize(
    "dia,hora,esperado",
    [
        (5, "21:30", False),   # antes de comecar
        (5, "22:00", True),    # borda de inicio
        (5, "23:59", True),    # noite
        (6, "00:30", True),    # madrugada — a janela comecou ONTEM
        (6, "03:00", True),
        (6, "06:00", True),    # borda de fim
        (6, "07:00", False),   # depois de terminar
    ],
)
def test_janela_atravessa_a_meia_noite(dia, hora, esperado):
    """22:00-06:00 e o periodo de sono. Antes, NENHUM instante casava."""
    casa = _timestamp_matches_agenda(_em(dia, hora), _agenda("22:00", "06:00"))
    assert casa is esperado, (
        f"{dia}/01 {hora} deveria {'' if esperado else 'NAO '}estar na janela noturna"
    )


def test_madrugada_pertence_ao_dia_em_que_a_janela_comecou():
    """Uma agenda de SEGUNDA 22:00-06:00 cobre a madrugada de TERCA.

    E a mesma ocorrencia da janela — quem marcou "segunda a noite" quis dizer a
    noite que termina na manha de terca. Checar o dia da semana contra a data do
    proprio timestamp cortaria a janela ao meio a meia-noite.
    """
    so_segunda = _agenda("22:00", "06:00", dias=[0])

    assert _timestamp_matches_agenda(_em(5, "23:00"), so_segunda) is True   # seg 23h
    assert _timestamp_matches_agenda(_em(6, "03:00"), so_segunda) is True   # ter 3h
    # A madrugada de segunda pertence a janela que comecou no DOMINGO, que nao
    # esta configurada:
    assert _timestamp_matches_agenda(_em(5, "03:00"), so_segunda) is False


def test_hora_invalida_e_rejeitada_no_cadastro():
    """Formato errado tem de estourar aqui, nao no motor de alertas.

    No motor o `strptime` cai no except de fail-safe, que so registra um
    warning: a agenda fica cadastrada e inerte, e ninguem descobre.
    """
    from pydantic import ValidationError

    from interface.endpoints_agenda import AgendaCreate

    with pytest.raises(ValidationError):
        AgendaCreate(tipo="refeicao", hora_inicio="8h", hora_fim="09:00")

    with pytest.raises(ValidationError):
        AgendaCreate(tipo="refeicao", dias_semana=[0, 9])


def test_modo_invalido_e_rejeitado_tambem_no_update():
    """`modo` fora da lista nao suprime nada e nao acusa erro."""
    from pydantic import ValidationError

    from interface.endpoints_agenda import AgendaUpdate

    with pytest.raises(ValidationError):
        AgendaUpdate(modo="supprimir")

    with pytest.raises(ValidationError):
        AgendaUpdate(hora_fim="24:00")
