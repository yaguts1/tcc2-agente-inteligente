"""Saude do monitoramento: ha dado chegando para cada paciente?

Por que existe
--------------
O motor de alertas e puramente orientado a evento: so processa quando dado
chega. Se o ESP32 morrer, o WiFi cair ou a ingestao quebrar, nao ha
processamento, nao ha alerta — e o dashboard mostra "Nenhum alerta ativo /
Todos os pacientes estao com reposicionamento em dia".

Ou seja, o sistema FALHA CALADO: silencio e indistinguivel de "esta tudo bem".
Num monitoramento de seguranca do paciente esse e o pior modo de falha
possivel, pior do que travar — travar e visivel.

Este modulo torna a AUSENCIA de dado observavel: a ultima leitura de cada
paciente e comparada com um limite, e quem passou do limite e reportado como
sem monitoramento.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from interface.db_core import connect
from interface.tempo import agora_utc_naive


def limite_silencio_min() -> int:
    """Minutos sem dado a partir dos quais o monitoramento e considerado
    interrompido.

    Default de 15 min: os dispositivos enviam em intervalo de segundos a
    poucos minutos, entao 15 absorve uma reconexao de WiFi sem gerar ruido,
    mas ainda detecta uma falha muito antes de virar risco clinico (a janela
    de reposicionamento mais curta e de 2h).
    """
    try:
        return max(1, int(os.getenv("MONITORAMENTO_LIMITE_MIN", "15")))
    except ValueError:
        return 15


def status_por_paciente(db_path: str, limite_min: int | None = None) -> list[dict[str, Any]]:
    """Situacao de monitoramento de cada paciente com leito atribuido.

    Considera apenas pacientes COM cama: quem nao esta num leito nao deveria
    estar sendo monitorado, e reporta-lo como "sem dados" seria ruido que
    ensina a equipe a ignorar o aviso.
    """
    limite = limite_silencio_min() if limite_min is None else limite_min
    agora = agora_utc_naive()
    corte = (agora - timedelta(minutes=limite)).strftime("%Y-%m-%dT%H:%M:%S")

    with connect(db_path) as conn:
        linhas = conn.execute(
            """
            SELECT f.paciente_id  AS paciente_id,
                   f.nome         AS nome,
                   f.cama_id      AS cama_id,
                   MAX(g.ts)      AS ultima_leitura
              FROM paciente_fichas f
              LEFT JOIN grade g ON g.paciente_id = f.paciente_id
             WHERE f.cama_id IS NOT NULL AND f.cama_id != ''
             GROUP BY f.paciente_id, f.nome, f.cama_id
            """
        ).fetchall()

    resultado = []
    for l in linhas:
        ultima = l["ultima_leitura"]
        silencioso = (ultima is None) or (str(ultima) < corte)
        minutos = None
        if ultima:
            try:
                from datetime import datetime

                minutos = int(
                    (agora - datetime.fromisoformat(str(ultima)[:19])).total_seconds() // 60
                )
            except (ValueError, TypeError):
                minutos = None
        resultado.append(
            {
                "paciente_id": l["paciente_id"],
                "nome": l["nome"],
                "cama_id": l["cama_id"],
                "ultima_leitura": ultima,
                "minutos_sem_dados": minutos,
                "monitorado": not silencioso,
                # `nunca` distingue "o sensor parou" de "nunca chegou dado
                # nenhum" — a segunda costuma ser erro de instalacao/vinculo,
                # e a acao corretiva e outra.
                "nunca_recebeu_dados": ultima is None,
            }
        )
    resultado.sort(key=lambda r: (r["monitorado"], r["paciente_id"]))
    return resultado


def resumo(db_path: str, limite_min: int | None = None) -> dict[str, Any]:
    """Resumo agregado, para o dashboard e para as metricas."""
    pacientes = status_por_paciente(db_path, limite_min)
    sem_dados = [p for p in pacientes if not p["monitorado"]]
    return {
        "limite_min": limite_silencio_min() if limite_min is None else limite_min,
        "total_com_leito": len(pacientes),
        "monitorados": len(pacientes) - len(sem_dados),
        "sem_monitoramento": len(sem_dados),
        "pacientes_sem_monitoramento": sem_dados,
    }
