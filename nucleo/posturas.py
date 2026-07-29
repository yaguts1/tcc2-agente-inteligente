"""Que sitios anatomicos cada postura carrega.

O motor tratava toda postura como intercambiavel: `postura != run_postura`
reiniciava a corrida, e nada dizia que supino carrega sacro e calcaneos —
os sitios da maioria das lesoes de estagio 3 e 4 — enquanto lateral a 90°
carrega o trocanter, que e precisamente a razao de o padrao de cuidado ser 30°
e nao 90°.

Duas consequencias do modelo antigo:

  * 60 min em supino e 60 min em lateral a 30° contavam igual, embora carreguem
    sitios diferentes (e o segundo, quase nenhum dos criticos);

  * o reset era EXPLORAVEL POR RUIDO. `lateral_direito -> supino ->
    lateral_direito` em 6 minutos zerava a janela inteira sem que o trocanter
    tivesse sido aliviado de verdade: 1 minuto de supino nao descarrega um
    trocanter que ficou 50 minutos sob pressao.

O MAPA ABAIXO E UMA SIMPLIFICACAO DELIBERADA, e precisa ser lida como tal: e
uma aproximacao clinica razoavel do que suporta o peso em cada decubito, nao uma
medida. A distribuicao real depende de IMC, contraturas, dispositivos e
superficie de apoio. O valor dele nao esta na precisao — esta em distinguir
sitios que antes eram indistinguiveis. Um mapa por paciente (contraturas,
amputacao, retalho) e evolucao natural daqui.

Os nomes de sitio sao os MESMOS de `interface/repositories/lesoes.py`, de
proposito: e o que permite cruzar "onde a carga se acumulou" com "onde a lesao
apareceu". Dois vocabularios para a mesma anatomia tornariam esse cruzamento
impossivel.
"""
from __future__ import annotations

SUPINO = "supino"
PRONO = "prono"
LATERAL_DIREITO = "lateral_direito"
LATERAL_ESQUERDO = "lateral_esquerdo"
LATERAL_DIREITO_30 = "lateral_direito_30"
LATERAL_ESQUERDO_30 = "lateral_esquerdo_30"
SENTADO = "sentado"
SEMI_FOWLER = "semi_fowler"

# Sitios sob carga em cada postura.
#
# Nota sobre os 30°: a posicao lateral a 30° existe justamente para NAO apoiar
# no trocanter — o peso vai para a massa glutea, que tolera pressao muito melhor.
# Por isso ela carrega menos sitios criticos que o lateral a 90°, e e o que o
# protocolo recomenda. Um modelo que tratasse as duas igual nao teria como
# mostrar essa diferenca, que e a principal recomendacao pratica da area.
SITIOS_POR_POSTURA: dict[str, frozenset[str]] = {
    SUPINO: frozenset({
        "sacro", "calcaneo_esquerdo", "calcaneo_direito",
        "occipital", "escapula_esquerda", "escapula_direita",
        "cotovelo_esquerdo", "cotovelo_direito",
    }),
    PRONO: frozenset({
        "nariz", "orelha_esquerda", "orelha_direita",
        "cotovelo_esquerdo", "cotovelo_direito",
    }),
    LATERAL_DIREITO: frozenset({
        "trocanter_direito", "maleolo_direito", "orelha_direita",
    }),
    LATERAL_ESQUERDO: frozenset({
        "trocanter_esquerdo", "maleolo_esquerdo", "orelha_esquerda",
    }),
    LATERAL_DIREITO_30: frozenset({"maleolo_direito"}),
    LATERAL_ESQUERDO_30: frozenset({"maleolo_esquerdo"}),
    # Sentado transfere a carga para os isquios, e a cabeceira elevada soma
    # cisalhamento no sacro — o mecanismo por tras de boa parte das lesoes
    # sacrais, e a razao de a recomendacao ser manter a cabeceira abaixo de 30°.
    SENTADO: frozenset({"isquio_esquerdo", "isquio_direito", "coccige", "sacro"}),
    SEMI_FOWLER: frozenset({"sacro", "calcaneo_esquerdo", "calcaneo_direito"}),
}

POSTURAS_CONHECIDAS = frozenset(SITIOS_POR_POSTURA)

# Prefixo dos sitios sinteticos criados para postura desconhecida. Ver
# `sitios_sob_carga`.
PREFIXO_SITIO_SINTETICO = "postura:"


def normalizar(postura: str) -> str:
    return str(postura or "").strip().lower()


def sitios_sob_carga(postura: str) -> frozenset[str]:
    """Sitios que esta postura carrega.

    Postura DESCONHECIDA devolve um sitio sintetico com o proprio nome dela, e
    isso e o ponto: a carga passa a acumular por "aquela postura", e o
    comportamento resultante e IDENTICO ao modelo antigo de corrida por postura.

    Ou seja, um firmware que envie um rotulo que este mapa nao conhece nao perde
    monitoramento nem passa a alertar diferente — degrada exatamente para o que
    o sistema fazia antes. Sem isso, a alternativa seria escolher entre ignorar a
    amostra (paciente sem vigilancia) ou carregar todos os sitios (alarme
    constante), e as duas sao piores que continuar como estava.
    """
    normalizada = normalizar(postura)
    conhecidos = SITIOS_POR_POSTURA.get(normalizada)
    if conhecidos is not None:
        return conhecidos
    return frozenset({f"{PREFIXO_SITIO_SINTETICO}{normalizada}"})


def e_sitio_sintetico(sitio: str) -> bool:
    return str(sitio).startswith(PREFIXO_SITIO_SINTETICO)


def descrever_sitio(sitio: str) -> str:
    """Rotulo legivel, para o alerta poder dizer ONDE a carga se acumulou."""
    if e_sitio_sintetico(sitio):
        return str(sitio)[len(PREFIXO_SITIO_SINTETICO):].replace("_", " ")
    return str(sitio).replace("_", " ")


# Prioridade clinica dos sitios, do mais para o menos grave.
#
# Serve de DESEMPATE quando varios sitios tem a mesma carga acumulada — o que e
# o caso comum, porque uma postura carrega vários de uma vez. Supino carrega
# sacro, calcaneos, occipital, escapulas e cotovelos ao MESMO tempo e pelo mesmo
# intervalo, entao o alerta precisa escolher qual nomear.
#
# Desempatar por ordem alfabetica seria deterministico e clinicamente inutil:
# nomearia "calcaneo_direito" num paciente cujo problema e o sacro. E o nome no
# alerta e o que diz PARA QUAL LADO virar.
#
# A ordem segue gravidade e incidencia: sacro e trocanter concentram a maioria
# das lesoes de estagio 3 e 4; calcaneo vem em seguida e e o mais subestimado
# (coxim resolve, e quase nunca e usado); os demais sao menos frequentes ou mais
# superficiais.
PRIORIDADE_CLINICA: tuple[str, ...] = (
    "sacro",
    "coccige",
    "trocanter_direito",
    "trocanter_esquerdo",
    "isquio_direito",
    "isquio_esquerdo",
    "calcaneo_direito",
    "calcaneo_esquerdo",
    "occipital",
    "maleolo_direito",
    "maleolo_esquerdo",
    "escapula_direita",
    "escapula_esquerda",
    "cotovelo_direito",
    "cotovelo_esquerdo",
    "orelha_direita",
    "orelha_esquerda",
    "nariz",
)

_ORDEM = {sitio: posicao for posicao, sitio in enumerate(PRIORIDADE_CLINICA)}


def prioridade(sitio: str) -> int:
    """Posicao do sitio na ordem clinica. Menor = mais grave.

    Sitio fora da lista (inclusive os sinteticos de postura desconhecida) vai
    para o fim, mas continua comparavel: um alerta sobre postura desconhecida
    vale mais que nenhum alerta.
    """
    return _ORDEM.get(str(sitio), len(PRIORIDADE_CLINICA))
