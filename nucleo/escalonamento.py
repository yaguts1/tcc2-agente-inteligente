"""Quanto tempo um alerta ficou aberto, e o que isso deveria mudar.

Hoje um alerta aberto as 03:00 renderiza IGUAL as 07:00 — mesma cor, mesmo
peso, mesma posicao. A unica diferenca e um numero maior em `getTimeUntil`, que
e texto no meio de uma linha. Quatro horas de imobilidade continua nao sao "um
pouco pior" que trinta minutos: sao a diferenca entre um atraso e uma lesao.

O backend ja tinha o instinto certo — `repositories/alertas.py` isenta
DELIBERADAMENTE alertas nao resolvidos da janela temporal, com um bom
comentario, justamente para que um alerta antigo nao desapareca da tela. Mas
nada consumia isso: o alerta ficava, e ficava igual.

MODULO PURO, de proposito. Nada de banco, relogio ou I/O: recebe o perfil, os
minutos em aberto e o status, devolve o nivel. Isso permite:

  * o mesmo calculo no backend (que decide renotificar) e na resposta da API
    (que a tela ordena e colore), sem duas implementacoes divergindo;
  * teste por propriedade, como `nucleo/decisor.py` — ver
    `tests/test_escalonamento.py`.

POR QUE MULTIPLOS DA JANELA, e nao minutos fixos. A janela ja e a prescricao
clinica daquele paciente: 60 min para alto risco, 120 para baixo. Um limiar
fixo de "2 horas em aberto" trataria os dois igual, quando a mesma duracao
significa coisas diferentes — 2h de imobilidade em quem tem Braden 10 e outra
coisa que 2h em quem tem Braden 18. Escalonar em multiplos preserva a
proporcao que o Braden estabeleceu.
"""

from __future__ import annotations

from typing import Literal

Nivel = Literal["normal", "atencao", "critico", "violacao"]

# Multiplos da janela de reposicionamento do paciente.
#
# `atencao` em 1x: o alerta abre quando a janela e atingida, entao 1x significa
# "ja se passou uma janela inteira DEPOIS de o alerta abrir" — o paciente esta
# ha duas janelas sem alivio naquele sitio.
#
# `violacao` em 3x nao e limiar clinico e sim ORGANIZACIONAL: a essa altura a
# questao deixou de ser o paciente e passou a ser o processo. Alguem precisa
# saber que a ala nao esta conseguindo responder, e isso e um dado de gestao,
# nao de beira de leito.
LIMIARES: tuple[tuple[float, Nivel], ...] = (
    (3.0, "violacao"),
    (2.0, "critico"),
    (1.0, "atencao"),
)

# Nivel numerico, para comparacao e ordenacao. Exportado porque a tela precisa
# ordenar por gravidade e o backend precisa saber se o nivel SUBIU desde a
# ultima notificacao.
ORDEM: dict[Nivel, int] = {"normal": 0, "atencao": 1, "critico": 2, "violacao": 3}


def nivel(
    *,
    janela_min: int,
    minutos_aberto: float,
    status: str = "aberto",
) -> Nivel:
    """O nivel de escalonamento de um alerta.

    `status` importa: um alerta RECONHECIDO nao escala alem de `atencao`.
    Alguem assumiu, e continuar subindo o tom sobre um alerta que ja tem dono
    e o mecanismo exato pelo qual sistemas de alarme clinico sao desligados —
    a equipe aprende que o vermelho nao significa nada porque ele aparece mesmo
    quando ela esta agindo.

    Alerta FECHADO e sempre `normal`: ele so aparece em historico.
    """
    if status in ("fechado", "completed"):
        return "normal"
    if janela_min <= 0 or minutos_aberto < 0:
        # Sem janela valida nao ha proporcao a aplicar. Nao levanta: dado
        # historico incompleto nao pode derrubar a listagem de alertas.
        return "normal"

    proporcao = minutos_aberto / janela_min
    resultado: Nivel = "normal"
    for limiar, candidato in LIMIARES:
        if proporcao >= limiar:
            resultado = candidato
            break

    if status in ("reconhecido", "acknowledged") and ORDEM[resultado] > ORDEM["atencao"]:
        return "atencao"
    return resultado


def escalou(anterior: Nivel | None, atual: Nivel) -> bool:
    """Se houve SUBIDA de nivel — o gatilho de renotificacao.

    Renotificar por nivel, e nao por intervalo fixo, e o que evita as duas
    falhas opostas: repetir a cada N minutos treina a equipe a ignorar, e nunca
    repetir faz o alerta das 03:00 desaparecer no ruido ate o turno seguinte.
    Aqui o aviso volta exatamente quando algo MUDOU.

    `anterior is None` conta como subida a partir de `normal`: e o primeiro
    calculo para aquele alerta.
    """
    return ORDEM[atual] > ORDEM[anterior or "normal"]
