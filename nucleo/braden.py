"""Escala de Braden: o instrumento que a enfermagem ja usa.

O risco, neste sistema, era um enum de tres valores num dropdown — `baixo`,
`medio`, `alto` — sem escore, sem subescores, sem data de reavaliacao e sem
registro de quem classificou. As janelas de reposicionamento (60/90/120 min)
eram variaveis de ambiente GLOBAIS, e nada no repositorio citava fonte para
esses numeros.

Por que isso importa mais do que parece: numa ala brasileira, BRADEN E O QUE VAI
PARA O PRONTUARIO (Protocolo de Prevencao de Lesao por Pressao, MS/ANVISA/
FIOCRUZ 2013). Uma ferramenta que nao consome Braden pede que a enfermeira
mantenha uma SEGUNDA classificacao de risco, paralela e sem justificativa, ao
lado da que ela ja e obrigada a registrar. Duas classificacoes divergem, e a
que este sistema usava era a que ninguem auditava.

Este modulo e puro: so aritmetica e faixas. A persistencia fica em
`interface/repositories/braden.py`.

FONTES DAS FAIXAS
-----------------
As faixas de risco sao as da escala original (Bergstrom et al., 1987), na forma
adotada pelo protocolo brasileiro. Elas ficam explicitas aqui, com o nome, para
que a proxima pessoa possa CONFERIR — que era exatamente o que nao dava para
fazer com `JANELA_ALTO=60` numa variavel de ambiente.
"""
from __future__ import annotations

from typing import Mapping

# Os seis subescores. Cinco vao de 1 a 4; friccao/cisalhamento vai de 1 a 3 — e
# nao e detalhe de digitacao: aceitar 4 ali inflaria o total e poderia rebaixar
# o paciente de faixa de risco sem ninguem perceber.
SUBESCALAS: dict[str, tuple[int, int]] = {
    "percepcao_sensorial": (1, 4),
    "umidade": (1, 4),
    "atividade": (1, 4),
    "mobilidade": (1, 4),
    "nutricao": (1, 4),
    "friccao_cisalhamento": (1, 3),
}

TOTAL_MINIMO = sum(minimo for minimo, _ in SUBESCALAS.values())   # 6
TOTAL_MAXIMO = sum(maximo for _, maximo in SUBESCALAS.values())   # 23

# Faixas de risco. MENOR escore = MAIOR risco — o contrario da intuicao de quem
# le "escore alto e ruim", e uma inversao que ja causou erro em varios sistemas.
# O limite superior de cada faixa e inclusivo.
FAIXA_SEM_RISCO = "sem_risco"
FAIXA_BAIXO = "baixo"
FAIXA_MODERADO = "moderado"
FAIXA_ALTO = "alto"
FAIXA_MUITO_ALTO = "muito_alto"

_FAIXAS: tuple[tuple[int, str], ...] = (
    (9, FAIXA_MUITO_ALTO),   # <= 9
    (12, FAIXA_ALTO),        # 10-12
    (14, FAIXA_MODERADO),    # 13-14
    (18, FAIXA_BAIXO),       # 15-18
    (TOTAL_MAXIMO, FAIXA_SEM_RISCO),  # >= 19
)

# Faixa de Braden -> perfil deste sistema.
#
# O sistema tem TRES perfis (`baixo`/`medio`/`alto`, com janelas de 120/90/60
# min) e Braden tem CINCO faixas. O mapeamento colapsa as pontas:
#
#   * `muito_alto` e `alto` viram `alto`. Nao ha janela mais curta que 60 min
#     para oferecer, e fingir uma granularidade que o motor nao tem seria pior
#     que colapsar — a enfermeira veria uma distincao sem efeito nenhum;
#   * `sem_risco` vira `baixo`, e nao "nenhum monitoramento". Braden >= 19 e
#     baixa probabilidade, nao ausencia de risco, e um paciente monitorado a
#     cada 120 min custa quase nada.
#
# A faixa ORIGINAL fica registrada junto da avaliacao, entao o colapso nao
# apaga informacao — so nao a usa para decidir a janela ainda.
PERFIL_POR_FAIXA: dict[str, str] = {
    FAIXA_MUITO_ALTO: "alto",
    FAIXA_ALTO: "alto",
    FAIXA_MODERADO: "medio",
    FAIXA_BAIXO: "baixo",
    FAIXA_SEM_RISCO: "baixo",
}


class BradenInvalido(ValueError):
    """Subescores fora do intervalo, ou faltando."""


def validar(subescores: Mapping[str, int]) -> dict[str, int]:
    """Confere os seis subescores e devolve-os normalizados.

    Recusa subescore FALTANDO em vez de assumir um valor. Um Braden com cinco
    dos seis campos nao e um Braden — e o total resultante colocaria o paciente
    numa faixa de risco mais leve do que a real, que e o erro que mais importa
    evitar aqui.
    """
    faltando = sorted(set(SUBESCALAS) - set(subescores))
    if faltando:
        raise BradenInvalido(f"subescores faltando: {faltando}")

    sobrando = sorted(set(subescores) - set(SUBESCALAS))
    if sobrando:
        raise BradenInvalido(f"subescores desconhecidos: {sobrando}")

    normalizados: dict[str, int] = {}
    for nome, (minimo, maximo) in SUBESCALAS.items():
        try:
            valor = int(subescores[nome])
        except (TypeError, ValueError) as exc:
            raise BradenInvalido(f"{nome}: valor nao numerico") from exc
        if not minimo <= valor <= maximo:
            raise BradenInvalido(
                f"{nome}: {valor} fora do intervalo {minimo}-{maximo}"
            )
        normalizados[nome] = valor
    return normalizados


def total(subescores: Mapping[str, int]) -> int:
    return sum(validar(subescores).values())


def faixa(escore: int) -> str:
    """Faixa de risco de um total de Braden.

    MENOR escore = MAIOR risco. A inversao e contraintuitiva o suficiente para
    ter causado erro em outros sistemas, e e o motivo de esta funcao existir em
    vez de a comparacao ficar espalhada.
    """
    if not TOTAL_MINIMO <= escore <= TOTAL_MAXIMO:
        raise BradenInvalido(
            f"escore {escore} fora do intervalo {TOTAL_MINIMO}-{TOTAL_MAXIMO}"
        )
    for limite, nome in _FAIXAS:
        if escore <= limite:
            return nome
    return FAIXA_SEM_RISCO


def perfil_para(escore: int) -> str:
    """Perfil deste sistema (`baixo`/`medio`/`alto`) para um total de Braden."""
    return PERFIL_POR_FAIXA[faixa(escore)]


def avaliar(subescores: Mapping[str, int]) -> dict:
    """Total, faixa e perfil derivado — numa passada."""
    normalizados = validar(subescores)
    escore = sum(normalizados.values())
    nome_faixa = faixa(escore)
    return {
        "subescores": normalizados,
        "total": escore,
        "faixa": nome_faixa,
        "perfil": PERFIL_POR_FAIXA[nome_faixa],
    }
