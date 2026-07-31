"""Propriedades da escada de escalonamento.

`nucleo/escalonamento.py` e puro, entao vale o mesmo tratamento que o decisor:
gerar entrada e barato e o oraculo e exato.

O que se protege aqui e menos obvio que "o calculo esta certo". A escada existe
para resolver um problema de ATENCAO HUMANA, e as duas maneiras de errar sao
simetricas e igualmente caras:

  * escalar de menos, e o alerta das 03:00 chega as 07:00 igual ao das 06:55;
  * escalar demais, e a equipe aprende que vermelho nao significa nada.

A segunda e a que mata sistemas de alarme clinico, e e a que as propriedades
sobre `status` cobrem.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from nucleo.escalonamento import ORDEM, Nivel, escalou, nivel

JANELAS = st.sampled_from([60, 90, 120])
MINUTOS = st.floats(min_value=0, max_value=2000, allow_nan=False, allow_infinity=False)
ABERTOS = st.sampled_from(["aberto", "pending", "reconhecido", "acknowledged"])

RAPIDO = settings(max_examples=300, deadline=None)


@given(janela=JANELAS, minutos=MINUTOS, status=ABERTOS)
@RAPIDO
def test_o_nivel_nunca_cai_com_o_tempo(janela, minutos, status):
    """Monotonicidade: mais tempo em aberto nunca DIMINUI a gravidade.

    Parece trivial e nao e — foi a primeira coisa que quis travar. Um limiar
    escrito na ordem errada (procurando o menor multiplo primeiro) produziria
    uma escada que sobe e desce, e o sintoma seria um alerta piscando entre
    vermelho e amarelo enquanto ninguem o atende. Isso e pior que nao ter
    escada, porque parece defeito da tela e destroi a confianca no resto.
    """
    agora = nivel(janela_min=janela, minutos_aberto=minutos, status=status)
    depois = nivel(janela_min=janela, minutos_aberto=minutos + 1, status=status)
    assert ORDEM[depois] >= ORDEM[agora]


@given(janela=JANELAS, minutos=MINUTOS)
@RAPIDO
def test_reconhecer_impede_a_escalada_mas_nao_apaga_o_alerta(janela, minutos):
    """O mecanismo anti-fadiga.

    Continuar subindo o tom sobre um alerta que JA TEM DONO e exatamente como
    a equipe aprende que a cor nao significa nada. Mas ele tambem nao pode
    voltar a `normal`: alguem assumiu, e nao resolveu.
    """
    sem_dono = nivel(janela_min=janela, minutos_aberto=minutos, status="aberto")
    com_dono = nivel(janela_min=janela, minutos_aberto=minutos, status="reconhecido")

    assert ORDEM[com_dono] <= ORDEM[sem_dono]
    assert ORDEM[com_dono] <= ORDEM["atencao"]
    # E, crucialmente, nao zera o que ja era grave.
    if ORDEM[sem_dono] >= ORDEM["atencao"]:
        assert com_dono == "atencao"


@given(janela=JANELAS, minutos=MINUTOS)
@RAPIDO
def test_alerta_fechado_nunca_escala(janela, minutos):
    """Alerta fechado so aparece em historico. Colori-lo de vermelho num
    relatorio de ontem sugere pendencia onde nao ha."""
    assert nivel(janela_min=janela, minutos_aberto=minutos, status="fechado") == "normal"


@given(janela=JANELAS, minutos=MINUTOS, status=ABERTOS)
@RAPIDO
def test_a_proporcao_e_o_que_manda_e_nao_o_relogio(janela, minutos, status):
    """A mesma PROPORCAO da mesma gravidade, em qualquer perfil.

    E a razao de a escada ser em multiplos da janela. Um limiar fixo de "2h em
    aberto" trataria igual o Braden 10 e o Braden 18, quando a mesma duracao
    significa coisas diferentes — a janela ja e a prescricao daquele paciente,
    e escalonar em multiplos preserva a proporcao que o Braden estabeleceu.
    """
    assume(janela != 60)
    proporcional = minutos * janela / 60

    assert nivel(janela_min=60, minutos_aberto=minutos, status=status) == nivel(
        janela_min=janela, minutos_aberto=proporcional, status=status
    )


@given(janela=JANELAS, status=ABERTOS)
@RAPIDO
def test_alerta_recem_aberto_e_normal(janela, status):
    """A escada nao pode comecar acesa: alerta que acabou de abrir ja e um
    aviso, e pinta-lo de critico na primeira renderizacao gastaria o vermelho
    no caso mais comum."""
    assert nivel(janela_min=janela, minutos_aberto=0, status=status) == "normal"


@given(janela=JANELAS, minutos=MINUTOS, status=ABERTOS)
@RAPIDO
def test_nunca_levanta_e_sempre_devolve_nivel_conhecido(janela, minutos, status):
    """Dado historico incompleto nao pode derrubar a listagem de alertas — a
    tela inteira e a consequencia."""
    assert nivel(janela_min=janela, minutos_aberto=minutos, status=status) in ORDEM


@pytest.mark.parametrize("janela_invalida", [0, -1, -60])
def test_janela_invalida_degrada_para_normal(janela_invalida):
    """Alertas antigos podem nao ter janela util. Sem proporcao nao ha escada,
    e o certo e nao afirmar gravidade que nao se sabe."""
    assert nivel(janela_min=janela_invalida, minutos_aberto=500) == "normal"


# ---------------------------------------------------------------------------
# Os limiares, em numeros concretos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutos", "esperado"),
    [
        (0, "normal"),
        (59, "normal"),
        (60, "atencao"),    # uma janela inteira DEPOIS de o alerta abrir
        (119, "atencao"),
        (120, "critico"),
        (179, "critico"),
        (180, "violacao"),  # limiar organizacional, nao clinico
        (600, "violacao"),
    ],
)
def test_limiares_para_perfil_de_alto_risco(minutos, esperado):
    """Perfil alto, janela de 60 min. Os numeros escritos por extenso porque as
    propriedades acima verificam a FORMA da escada e nao onde ela pisa."""
    assert nivel(janela_min=60, minutos_aberto=minutos) == esperado


# ---------------------------------------------------------------------------
# Renotificacao
# ---------------------------------------------------------------------------


@given(
    anterior=st.sampled_from(list(ORDEM)),
    atual=st.sampled_from(list(ORDEM)),
)
@RAPIDO
def test_so_renotifica_quando_o_nivel_sobe(anterior: Nivel, atual: Nivel):
    """Renotificar por MUDANCA, e nao por intervalo fixo.

    As duas falhas opostas: repetir a cada N minutos treina a equipe a ignorar,
    e nunca repetir faz o alerta das 03:00 sumir no ruido ate o turno seguinte.
    Avisar na subida faz o aviso voltar exatamente quando algo mudou.
    """
    assert escalou(anterior, atual) == (ORDEM[atual] > ORDEM[anterior])


def test_o_primeiro_calculo_conta_como_subida():
    """Sem estado anterior, qualquer nivel acima de `normal` e novidade."""
    assert escalou(None, "atencao") is True
    assert escalou(None, "normal") is False
