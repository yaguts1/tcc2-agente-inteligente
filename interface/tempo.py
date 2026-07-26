"""Utilitários de tempo — invariante de timezone do sistema.

REGRA CANÔNICA: o banco guarda timestamps NAIVE em UTC.
- Eventos do ESP32 chegam como `ts_utc` e são normalizados para UTC naive
  (interface/schemas.py:EventPayload).
- A exibição converte UTC→local (ferramentas/exportador.py).

Portanto, qualquer "agora" usado para COMPARAR com timestamps do banco (janela
de alertas, duração, etc.) precisa ser UTC naive — não `datetime.now()` local,
que estaria deslocado do fuso do servidor.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Detecta "+HH:MM" / "-HH:MM" no fim da string.
_TEM_OFFSET = re.compile(r"[+-]\d{2}:\d{2}$")

# Fuso do hospital (para converter UTC→local em comparações com horários que
# humanos digitam, como as horas de uma agenda de supressão). Mesmo fuso que a
# exibição usa (ferramentas/exportador.py: America/Sao_Paulo).
TZ_LOCAL = ZoneInfo("America/Sao_Paulo")


def agora_utc_naive() -> datetime:
    """`agora` em UTC, naive e sem microssegundos — o mesmo referencial dos
    timestamps armazenados no banco."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def para_iso_utc(valor: str | datetime | None) -> str | None:
    """Converte um timestamp do banco (UTC naive) em ISO-8601 COM offset.

    O banco guarda naive ("2026-07-25T13:44:47"), o que é a convenção interna.
    Mas mandar isso para o cliente é ambíguo — e o JavaScript resolve a
    ambiguidade da pior forma: `new Date("2026-07-25T13:44:47")` interpreta uma
    string sem offset como hora LOCAL. Para um usuário em São Paulo (UTC-3), um
    instante que é 13:44 UTC aparecia na tela como 13:44 — três horas adiantado.

    Num sistema de reposicionamento isso é clínico, não cosmético: o horário
    exibido é o que a equipe usa para decidir quando virar o paciente.

    Acrescentar o offset explícito faz o browser converter corretamente para o
    fuso de quem está olhando, sem o frontend precisar saber de nada.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        dt = valor
    else:
        texto = str(valor).strip()
        if not texto:
            return None
        # Já vem com offset (ex.: eventos de timeline gravados com isoformat
        # aware). Nesse caso não há o que consertar — e reescrever quebraria.
        if texto.endswith("Z") or _TEM_OFFSET.search(texto):
            return texto
        try:
            dt = datetime.fromisoformat(texto[:19])
        except ValueError:
            return texto
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def utc_naive_para_local(dt: datetime) -> datetime:
    """Converte um datetime naive-UTC (como armazenado no banco) para o fuso
    local do hospital, retornando um datetime naive nesse fuso. Se `dt` já
    tiver tzinfo, respeita e converte."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_LOCAL).replace(tzinfo=None)
