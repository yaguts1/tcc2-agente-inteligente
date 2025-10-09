# tests/test_simulador.py
import pandas as pd
from dados_simulados.gerador import gerar_sessao_multi, gerar_sessao_simulada

POSTURAS_VALIDAS = {"supino", "lateral_direito", "lateral_esquerdo", "prono"}

def test_gera_df_basico():
    df = gerar_sessao_simulada(duracao_horas=1, seed=123, passo_min=10)

    # Tem dados e as colunas esperadas
    assert not df.empty
    assert list(df.columns) == ["timestamp", "postura"]

    # Timestamps vÃ¡lidos, ordenados e com passo constante
    ts = pd.to_datetime(df["timestamp"])
    assert ts.is_monotonic_increasing
    diffs = ts.diff().dropna().unique()
    assert len(diffs) == 1 and diffs[0] == pd.Timedelta(minutes=10)

    # Posturas dentro do conjunto permitido e sem nulos
    assert df["postura"].notna().all()
    assert set(df["postura"].unique()).issubset(POSTURAS_VALIDAS)


def test_reprodutibilidade_seed():
    df1 = gerar_sessao_simulada(duracao_horas=2, seed=111, passo_min=10)
    df2 = gerar_sessao_simulada(duracao_horas=2, seed=111, passo_min=10)
    pd.testing.assert_frame_equal(df1, df2)  # exatamente iguais


def test_qtd_linhas_grade():
    horas, passo = 3, 15
    esperado = int((horas * 60) / passo) + 1
    df = gerar_sessao_simulada(duracao_horas=horas, seed=1, passo_min=passo)
    assert len(df) == esperado


def test_gerar_sessao_multi_pacientes():
    df_grade, df_eventos = gerar_sessao_multi(pacientes=3, horas=1, passo_min=15, seed=99, perfil="medio")

    assert set(df_grade.columns) == {"paciente_id", "timestamp", "postura"}
    assert list(df_grade["paciente_id"].unique()) == ["P1", "P2", "P3"]
    assert df_grade.equals(df_grade.sort_values(["paciente_id", "timestamp"]).reset_index(drop=True))

    assert "paciente_id" in df_eventos.columns
    assert df_eventos["paciente_id"].nunique() == 3
    assert not df_eventos.empty
