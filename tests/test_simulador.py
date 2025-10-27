# tests/test_simulador.py
import pandas as pd
from dados_simulados.gerador import gerar_sessao_multi, gerar_sessao_simulada

POSTURAS_VALIDAS = {"supino", "lateral_direito", "lateral_esquerdo", "prono"}

def test_gera_df_basico():
    df_grade, contextos = gerar_sessao_simulada(duracao_horas=1, seed=123, passo_min=10)

    # Tem dados e as colunas esperadas
    assert not df_grade.empty
    assert "timestamp" in df_grade.columns
    assert "postura" in df_grade.columns

    # Timestamps válidos, ordenados e com passo constante
    ts = pd.to_datetime(df_grade["timestamp"])
    assert ts.is_monotonic_increasing
    diffs = ts.diff().dropna().unique()
    assert len(diffs) == 1 and diffs[0] == pd.Timedelta(minutes=10)

    # Posturas dentro do conjunto permitido e sem nulos
    assert df_grade["postura"].notna().all()
    assert set(df_grade["postura"].unique()).issubset(POSTURAS_VALIDAS)


def test_reprodutibilidade_seed():
    df1_grade, ctx1 = gerar_sessao_simulada(duracao_horas=2, seed=111, passo_min=10)
    df2_grade, ctx2 = gerar_sessao_simulada(duracao_horas=2, seed=111, passo_min=10)
    pd.testing.assert_frame_equal(df1_grade, df2_grade)  # exatamente iguais


def test_qtd_linhas_grade():
    horas, passo = 3, 15
    esperado = int((horas * 60) / passo) + 1
    df_grade, _ = gerar_sessao_simulada(duracao_horas=horas, seed=1, passo_min=passo)
    assert len(df_grade) == esperado


def test_gerar_sessao_multi_pacientes():
    grades_dict, contextos_dict, df_eventos = gerar_sessao_multi(
        pacientes=3, horas=1, passo_min=15, seed=99, perfil="medio"
    )

    # Verifica estrutura de grades
    assert len(grades_dict) == 3
    assert set(grades_dict.keys()) == {"PAC-0000", "PAC-0001", "PAC-0002"}
    
    for paciente_id, df_grade in grades_dict.items():
        assert "timestamp" in df_grade.columns
        assert "postura" in df_grade.columns
        assert set(df_grade["postura"].unique()).issubset(POSTURAS_VALIDAS)

    # Verifica contextos
    assert len(contextos_dict) == 3

    # Verifica eventos consolidados
    assert "paciente_id" in df_eventos.columns
    assert df_eventos["paciente_id"].nunique() == 3
    assert not df_eventos.empty
