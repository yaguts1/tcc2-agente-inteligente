"""O identificador composto de alerta, num lugar so.

Um alerta nao tem chave propria: a identidade dele e `(paciente_id, inicio)`, e
a API precisa de um identificador unico em texto para a URL. A juncao escolhida
foi `f"{paciente_id}__{inicio}"`.

O separador `__` so e seguro se `paciente_id` NUNCA o contiver — e ele era texto
livre, sem `pattern` nem `max_length`, indo direto para
`INSERT OR IGNORE INTO pacientes(id)` a partir de um payload de dispositivo.
Consequencias, verificadas:

  * um `paciente_id` contendo `__` faz `split("__", 1)` resolver para OUTRO
    alerta. Ex.: o id "A__2026-01-01T00:00:00" com inicio "X" gera
    "A__2026-01-01T00:00:00__X", que parte em ("A", "2026-01-01T00:00:00__X") —
    reconhecer um alerta acabaria escrevendo no registro de outro paciente;
  * um `paciente_id` contendo `/` faz a rota nem casar, porque a barra fecha o
    segmento da URL — e o frontend nao fazia `encodeURIComponent`.

A defesa e em duas camadas, de proposito:

  1. `PADRAO_PACIENTE_ID` recusa o caractere na BORDA (ver `interface/schemas.py`),
     que e onde o dado entra;
  2. `partir_alert_id` valida a forma na SAIDA, para um dado que ja esteja no
     banco de antes da validacao nao virar acesso cruzado.

Uma camada so nao basta: a primeira nao alcanca as linhas ja gravadas, e a
segunda nao impede que dado malformado continue entrando.
"""
from __future__ import annotations

import re

# `PAC-0001` e o formato gerado por `PatientRepository._generate_paciente_id`,
# mas o padrao e mais permissivo do que isso: bases legadas e importacoes usam
# outros prefixos, e recusa-los aqui rejeitaria dado clinico existente. O que
# ele garante e so o necessario — nada de `__`, nada de `/`, nada de espaco.
# Sem look-ahead: este padrao tambem e usado pelo pydantic, cujo motor de regex
# (Rust) nao suporta `(?!...)` — um `SchemaError` no import derrubaria a
# aplicacao inteira, e nao so a validacao.
#
# A construcao expressa "sem `__`" de outro jeito: um bloco sem underscore,
# seguido de zero ou mais (UM underscore + bloco sem underscore). Isso tambem
# recusa underscore no inicio e no fim, e `/` nunca entra porque nao esta em
# nenhuma classe.
PADRAO_PACIENTE_ID = r"^[A-Za-z0-9][A-Za-z0-9.-]*(_[A-Za-z0-9.-]+)*$"
_RE_PACIENTE_ID = re.compile(PADRAO_PACIENTE_ID)

SEPARADOR = "__"


class AlertIdInvalido(ValueError):
    """Identificador de alerta fora do formato esperado."""


def paciente_id_valido(paciente_id: str) -> bool:
    return bool(_RE_PACIENTE_ID.match(str(paciente_id or "")))


def montar_alert_id(paciente_id: str, inicio: str) -> str:
    return f"{paciente_id}{SEPARADOR}{inicio}"


def partir_alert_id(alert_id: str) -> tuple[str, str]:
    """Devolve (paciente_id, inicio) ou levanta `AlertIdInvalido`.

    `split(SEPARADOR, 1)` — pela ESQUERDA — porque `inicio` e um timestamp ISO,
    que nunca contem `__`, enquanto o `paciente_id` e a parte que poderia. Partir
    pela direita moveria o problema em vez de resolve-lo.
    """
    texto = str(alert_id or "")
    paciente_id, separador, inicio = texto.partition(SEPARADOR)
    if not separador or not paciente_id or not inicio:
        raise AlertIdInvalido(f"alert_id sem separador '{SEPARADOR}': {alert_id!r}")
    if not paciente_id_valido(paciente_id):
        raise AlertIdInvalido(f"paciente_id invalido em alert_id: {alert_id!r}")
    if SEPARADOR in inicio:
        # O `inicio` e um timestamp: `__` ali significa que o `paciente_id`
        # continha o separador e a divisao saiu no lugar errado.
        raise AlertIdInvalido(f"alert_id ambiguo: {alert_id!r}")
    return paciente_id, inicio
