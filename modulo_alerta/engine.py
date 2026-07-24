"""Motor de decisao de alertas para imobilidade em leito."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from nucleo.decisor import processar_alertas_lote
from interface.dao_agenda import is_timestamp_in_suppressed_period
from interface.dao import _connect
from configuracao import carregar_configuracao

config = carregar_configuracao()


def processar_alertas(
    df_grade: pd.DataFrame,
    perfil: str,
    paciente_id: str,
    min_conf: float = 0.0,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
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
            # Check if alert timestamp is in suppressed period
            timestamp_str = alerta.get("inicio", "")
            is_suppressed, modo = is_timestamp_in_suppressed_period(
                db_path=config.db_path,
                paciente_id=paciente_id,
                timestamp=timestamp_str,
            )
            
            if modo == "suprimir":
                # Skip this alert completely
                continue
            elif modo == "reduzir":
                # Reduce the alert's janela window
                reducao = _get_agenda_reducao_janela(paciente_id, timestamp_str)
                if reducao > 0:
                    alerta["janela_min"] = max(5, alerta.get("janela_min", 0) - reducao)
                    alerta["modo_supressao"] = "reduzido"
            # else modo == "monitorar": keep alert as-is
            
            alertas_filtrados.append(alerta)
        except Exception:
            # If suppression check fails, keep the alert (fail-safe)
            alertas_filtrados.append(alerta)

    return df_norm, alertas_filtrados


def _get_agenda_reducao_janela(paciente_id: str, timestamp_str: str) -> int:
    """Helper: Extract reduction window from agenda if available."""
    try:
        conn = _connect(config.db_path)
        cursor = conn.cursor()
        
        # Get all active agendas with reducao_janela_min for this patient at this timestamp
        cursor.execute("""
            SELECT MAX(reducao_janela_min) FROM agendas_paciente 
            WHERE paciente_id = ? 
            AND ativo = 1 
            AND modo = 'reduzir'
            AND deletado = 0
        """, (paciente_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else 0
    except Exception:
        return 0
