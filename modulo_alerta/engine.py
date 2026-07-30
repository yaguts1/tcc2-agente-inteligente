"""Motor de decisao de alertas para imobilidade em leito."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import structlog

from nucleo.decisor import processar_alertas_lote
from interface.dao_agenda import is_timestamp_in_suppressed_period, get_reducao_janela
from interface.tempo import utc_naive_para_local
from configuracao import carregar_configuracao

config = carregar_configuracao()
logger = structlog.get_logger(__name__)


def processar_alertas(
    df_grade: pd.DataFrame,
    perfil: str,
    paciente_id: str,
    min_conf: float = 0.0,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Processa a serie de posturas e calcula alertas de imobilidade."""
    _ = min_conf  # reservado para evolucoes futuras

    if "timestamp" not in df_grade.columns or "postura" not in df_grade.columns:
        raise ValueError("df_grade precisa conter as colunas 'timestamp' e 'postura'.")

    df_norm = df_grade.copy(deep=True)
    ts_series = pd.to_datetime(df_norm["timestamp"], errors="raise", utc=True).dt.tz_convert(None)

    if not ts_series.is_monotonic_increasing:
        raise ValueError("Timestamps devem estar em ordem crescente.")

    df_norm["timestamp"] = ts_series.dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Convertidos para numpy array (em vez de combinar Series diretamente) para
    # evitar alinhamento por indice: com indices nao-contiguos (ex. apos groupby
    # por paciente), montar o DataFrame a partir de Series cujos indices nao
    # coincidem produz NaN e duplica linhas. `.dt.to_pydatetime()` retorna um
    # ndarray em pandas 2.x e uma Series em pandas 3.x, entao normalizamos com
    # pd.Series(...).to_numpy() para funcionar nas duas versoes.
    timestamps_py = pd.Series(ts_series.dt.to_pydatetime()).to_numpy()
    posturas = df_norm["postura"].astype(str).to_numpy()
    dados_lote = pd.DataFrame({"timestamp": timestamps_py, "postura": posturas})

    alertas = processar_alertas_lote(dados_lote, perfil, paciente_id)

    # Apply agenda-based suppression/reduction
    alertas_filtrados = []
    for alerta in alertas:
        try:
            # O `inicio` do alerta é UTC naive; as horas da agenda são horário
            # LOCAL do hospital (o que a enfermagem digita). Convertemos para
            # local antes de casar com a agenda — senão a supressão dispararia
            # no horário errado (deslocado pelo offset do fuso).
            inicio_str = alerta.get("inicio", "")
            timestamp_local = utc_naive_para_local(datetime.fromisoformat(inicio_str[:19]))
            is_suppressed, modo = is_timestamp_in_suppressed_period(
                db_path=config.db_path,
                paciente_id=paciente_id,
                timestamp=timestamp_local,
            )

            if modo == "suprimir":
                # Skip this alert completely
                continue
            if modo == "reduzir":
                # Reduce the alert's janela window
                reducao = get_reducao_janela(config.db_path, paciente_id, timestamp_local)
                if reducao > 0:
                    alerta["janela_min"] = max(5, alerta.get("janela_min", 0) - reducao)
                    alerta["modo_supressao"] = "reduzido"
            # else modo == "monitorar": keep alert as-is

            alertas_filtrados.append(alerta)
        except Exception as exc:
            # Fail-safe: mantém o alerta se a checagem de agenda falhar — mas
            # NÃO engole em silêncio (o bug da coluna `deletado` inexistente
            # ficou escondido justamente por um except silencioso aqui).
            logger.warning(
                "agenda_suppression_falhou",
                paciente_id=paciente_id,
                inicio=alerta.get("inicio"),
                motivo=str(exc),
            )
            alertas_filtrados.append(alerta)

    return df_norm, alertas_filtrados
