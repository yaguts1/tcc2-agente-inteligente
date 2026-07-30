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
from interface.repositories.unidades import filtro_sql as filtro_de_unidades
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


def status_por_paciente(
    db_path: str, limite_min: int | None = None, unidades: set[int] | None = None
) -> list[dict[str, Any]]:
    """Situacao de monitoramento de cada paciente com leito atribuido.

    Considera apenas pacientes COM cama: quem nao esta num leito nao deveria
    estar sendo monitorado, e reporta-lo como "sem dados" seria ruido que
    ensina a equipe a ignorar o aviso.
    """
    limite = limite_silencio_min() if limite_min is None else limite_min
    agora = agora_utc_naive()
    corte = (agora - timedelta(minutes=limite)).strftime("%Y-%m-%dT%H:%M:%S")

    # `f.unidade_id` no filtro: o painel de monitoramento nomeia os leitos sem
    # leitura, entao sem escopo ele conta — e MOSTRA — leitos de outras alas.
    condicao, params = filtro_de_unidades(unidades, coluna="f.unidade_id")
    # Subconsulta correlacionada, e NAO `LEFT JOIN` com `MAX(g.ts)` e `GROUP BY`.
    #
    # As duas devolvem exatamente o mesmo — conferido. A diferenca e o plano: com
    # `GROUP BY`, o SQLite varre as linhas de grade de cada paciente para depois
    # agregar; com a subconsulta, ele faz UMA busca no indice
    # `idx_grade_paciente_ts_desc` e para no primeiro resultado, porque o indice
    # ja esta na ordem pedida.
    #
    # Medido com 30 leitos e 30 dias de amostras a cada 5 min (260 mil linhas):
    # 130 ms contra <1 ms. E esta consulta roda a cada `/api/stats`, que o
    # dashboard dispara a cada mudanca de alerta.
    #
    # A alternativa obvia seria cachear. Seria pior: este e o watchdog que
    # detecta sensor mudo, e servir resposta velha atrasa justamente a deteccao
    # de que parou de chegar dado — o unico numero do sistema cuja utilidade E
    # ser recente.
    with connect(db_path) as conn:
        linhas = conn.execute(
            "SELECT f.paciente_id  AS paciente_id,"
            "       f.nome         AS nome,"
            "       f.cama_id      AS cama_id,"
            "       (SELECT g.ts FROM grade g"
            "         WHERE g.paciente_id = f.paciente_id"
            "         ORDER BY g.ts DESC LIMIT 1) AS ultima_leitura"
            "  FROM paciente_fichas f"
            " WHERE f.cama_id IS NOT NULL AND f.cama_id != ''"
            f"{condicao}",
            params,
        ).fetchall()

    resultado = []
    for linha in linhas:
        ultima = linha["ultima_leitura"]
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
                "paciente_id": linha["paciente_id"],
                "nome": linha["nome"],
                "cama_id": linha["cama_id"],
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


def resumo(
    db_path: str, limite_min: int | None = None, unidades: set[int] | None = None
) -> dict[str, Any]:
    """Resumo agregado, para o dashboard e para as metricas.

    O watchdog de fundo (`lifespan_tasks`) chama SEM unidades, de proposito: a
    metrica `pacientes_sem_monitoramento` e sobre a instalacao inteira, e um
    sensor mudo na ala B nao pode sumir do Prometheus so porque quem abriu a
    tela era da ala A.
    """
    pacientes = status_por_paciente(db_path, limite_min, unidades=unidades)
    sem_dados = [p for p in pacientes if not p["monitorado"]]
    return {
        "limite_min": limite_silencio_min() if limite_min is None else limite_min,
        "total_com_leito": len(pacientes),
        "monitorados": len(pacientes) - len(sem_dados),
        "sem_monitoramento": len(sem_dados),
        "pacientes_sem_monitoramento": sem_dados,
    }
