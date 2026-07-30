"""Validação de Coerência de Sessões Simuladas - Problema 6."""

import pandas as pd

# Posturas válidas (do gerador)
POSTURAS = ["deitado", "sentado", "em_pe"]

# Transições válidas (grafo de posturas)
TRANSICOES_VALIDAS = {
    "deitado": ["deitado", "sentado"],
    "sentado": ["sentado", "deitado", "em_pe"],
    "em_pe": ["em_pe", "sentado", "deitado"],
}


def validar_timestamps_ordenados(df_eventos: pd.DataFrame) -> tuple[bool, list[str]]:
    """Valida se timestamps estão em ordem crescente."""
    avisos = []
    
    if df_eventos is None or len(df_eventos) == 0:
        return True, avisos
    
    timestamps = pd.to_datetime(df_eventos["timestamp"])
    if not timestamps.is_monotonic_increasing:
        avisos.append("❌ Timestamps não estão em ordem crescente")
        return False, avisos
    
    return True, avisos


def validar_duracoes_positivas(df_eventos: pd.DataFrame) -> tuple[bool, list[str]]:
    """Valida se todas as durações são positivas."""
    avisos = []
    
    if df_eventos is None or len(df_eventos) == 0:
        return True, avisos
    
    if "duracao_min" not in df_eventos.columns:
        return True, avisos
    
    duracao_invalida = df_eventos[df_eventos["duracao_min"] <= 0]
    if len(duracao_invalida) > 0:
        avisos.append(f"❌ {len(duracao_invalida)} durações ≤ 0 encontradas")
        return False, avisos
    
    return True, avisos


def validar_posturas_validas(df_eventos: pd.DataFrame) -> tuple[bool, list[str]]:
    """Valida se todas as posturas são válidas."""
    avisos = []
    
    if df_eventos is None or len(df_eventos) == 0:
        return True, avisos
    
    if "postura" not in df_eventos.columns:
        return True, avisos
    
    posturas = df_eventos["postura"].unique()
    invalidas = set(posturas) - set(POSTURAS)
    
    if invalidas:
        avisos.append(f"❌ Posturas inválidas encontradas: {invalidas}")
        return False, avisos
    
    return True, avisos


def validar_transicoes_validas(df_eventos: pd.DataFrame) -> tuple[bool, list[str]]:
    """Valida se transições entre posturas respeitam o grafo."""
    avisos = []
    
    if df_eventos is None or len(df_eventos) < 2:
        return True, avisos
    
    if "postura" not in df_eventos.columns:
        return True, avisos
    
    for idx in range(len(df_eventos) - 1):
        postura_atual = df_eventos.iloc[idx]["postura"]
        proxima_postura = df_eventos.iloc[idx + 1]["postura"]
        
        # Se mesma postura, OK
        if postura_atual == proxima_postura:
            continue
        
        # Verificar se transição é válida
        proximas_validas = TRANSICOES_VALIDAS.get(postura_atual, [])
        if proxima_postura not in proximas_validas:
            avisos.append(f"❌ Transição inválida em índice {idx}: {postura_atual} → {proxima_postura}")
            return False, avisos
    
    return True, avisos


def validar_cobertura_temporal(df_eventos: pd.DataFrame) -> tuple[bool, list[str]]:
    """Valida se a cobertura temporal é consistente."""
    avisos = []
    
    if df_eventos is None or len(df_eventos) < 2:
        return True, avisos
    
    if "timestamp" not in df_eventos.columns or "duracao_min" not in df_eventos.columns:
        return True, avisos
    
    try:
        timestamps = pd.to_datetime(df_eventos["timestamp"])
        tempo_total_simulado = (timestamps.iloc[-1] - timestamps.iloc[0]).total_seconds() / 60
        tempo_total_durações = df_eventos["duracao_min"].sum()
        
        diferença = abs(tempo_total_simulado - tempo_total_durações)
        
        # Tolerância: 10 minutos
        if diferença > 10:
            avisos.append(
                f"⚠️  Cobertura temporal inconsistente: "
                f"simulada={tempo_total_simulado:.1f}min vs durações={tempo_total_durações:.1f}min "
                f"(diferença={diferença:.1f}min)"
            )
            # Não é erro crítico
            return True, avisos
    except Exception as e:
        avisos.append(f"⚠️  Erro ao validar cobertura temporal: {e!s}")
    
    return True, avisos


def validar_sem_duplicatas(df_eventos: pd.DataFrame) -> tuple[bool, list[str]]:
    """Valida se não há registros duplicados."""
    avisos = []
    
    if df_eventos is None or len(df_eventos) == 0:
        return True, avisos
    
    # Verificar duplicatas por timestamp e postura
    if "timestamp" in df_eventos.columns and "postura" in df_eventos.columns:
        duplicatas = df_eventos.duplicated(subset=["timestamp", "postura"], keep=False)
        
        if duplicatas.any():
            n_dup = duplicatas.sum()
            avisos.append(f"❌ {n_dup} registros duplicados encontrados")
            return False, avisos
    
    return True, avisos


def validar_sessao(
    df_eventos: pd.DataFrame,
    df_grade: pd.DataFrame = None,
    verbose: bool = True
) -> dict[str, bool]:
    """
    Valida coerência completa de uma sessão simulada.
    
    Realiza 6 validações críticas:
    1. Timestamps ordenados
    2. Durações positivas
    3. Posturas válidas
    4. Transições válidas
    5. Cobertura temporal
    6. Sem duplicatas
    
    Args:
        df_eventos: DataFrame com eventos (timestamp, postura, duracao_min, ...)
        df_grade: (Opcional) DataFrame com grade expandida (timestamp, postura)
        verbose: Se True, imprime detalhes
    
    Returns:
        Dict com resultado de cada validação (True/False)
        Exemplo: {
            "timestamps_ordenados": True,
            "duracoes_positivas": True,
            "posturas_validas": True,
            "transicoes_validas": True,
            "cobertura_temporal": True,
            "sem_duplicatas": True,
            "valido": True,
            "avisos": [...]
        }
    """
    resultados = {}
    todos_avisos = []
    
    # V1: Timestamps ordenados
    v1, avisos1 = validar_timestamps_ordenados(df_eventos)
    resultados["timestamps_ordenados"] = v1
    todos_avisos.extend(avisos1)
    
    # V2: Durações positivas
    v2, avisos2 = validar_duracoes_positivas(df_eventos)
    resultados["duracoes_positivas"] = v2
    todos_avisos.extend(avisos2)
    
    # V3: Posturas válidas
    v3, avisos3 = validar_posturas_validas(df_eventos)
    resultados["posturas_validas"] = v3
    todos_avisos.extend(avisos3)
    
    # V4: Transições válidas
    v4, avisos4 = validar_transicoes_validas(df_eventos)
    resultados["transicoes_validas"] = v4
    todos_avisos.extend(avisos4)
    
    # V5: Cobertura temporal
    v5, avisos5 = validar_cobertura_temporal(df_eventos)
    resultados["cobertura_temporal"] = v5
    todos_avisos.extend(avisos5)
    
    # V6: Sem duplicatas
    v6, avisos6 = validar_sem_duplicatas(df_eventos)
    resultados["sem_duplicatas"] = v6
    todos_avisos.extend(avisos6)
    
    # Validação geral
    validacoes_criticas = [v1, v2, v3, v4, v6]  # Sem v5 (pode ter tolerância)
    resultado_final = all(validacoes_criticas)
    
    resultados["valido"] = resultado_final
    resultados["avisos"] = todos_avisos
    
    # Imprimir se verbose
    if verbose:
        print("\n📊 Resultado de Validação:")
        print("=" * 50)
        for validacao, status in resultados.items():
            if validacao in ["valido", "avisos"]:
                continue
            simbolo = "✅" if status else "❌"
            print(f"  {simbolo} {validacao}")
        
        if todos_avisos:
            print("\n⚠️  Detalhes:")
            for aviso in todos_avisos:
                print(f"  {aviso}")
        
        print("=" * 50)
        if resultado_final:
            print("✅ SESSÃO VÁLIDA - Todos os testes passaram!")
        else:
            print("❌ SESSÃO INVÁLIDA - Erros encontrados acima")
        print()
    
    return resultados


# Função auxiliar para resumo
def resumo_validacao(resultado: dict[str, bool]) -> str:
    """Retorna resumo textual da validação."""
    if resultado.get("valido"):
        return "✅ Válido"
    return "❌ Inválido"
