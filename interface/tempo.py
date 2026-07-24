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

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Fuso do hospital (para converter UTC→local em comparações com horários que
# humanos digitam, como as horas de uma agenda de supressão). Mesmo fuso que a
# exibição usa (ferramentas/exportador.py: America/Sao_Paulo).
TZ_LOCAL = ZoneInfo("America/Sao_Paulo")


def agora_utc_naive() -> datetime:
    """`agora` em UTC, naive e sem microssegundos — o mesmo referencial dos
    timestamps armazenados no banco."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def utc_naive_para_local(dt: datetime) -> datetime:
    """Converte um datetime naive-UTC (como armazenado no banco) para o fuso
    local do hospital, retornando um datetime naive nesse fuso. Se `dt` já
    tiver tzinfo, respeita e converte."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_LOCAL).replace(tzinfo=None)
