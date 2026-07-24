"""Testes para Validação de Coerência (Problema 6)."""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from dados_simulados.validador import (
    validar_timestamps_ordenados,
    validar_duracoes_positivas,
    validar_posturas_validas,
    validar_transicoes_validas,
    validar_cobertura_temporal,
    validar_sem_duplicatas,
    validar_sessao,
)


class TestValidarTimestampsOrdenados:
    """Testes para validação de timestamps."""
    
    def test_timestamps_validos(self):
        """Timestamps em ordem crescente."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=5, freq="1h"),
            "postura": ["deitado"] * 5,
            "duracao_min": [60] * 5,
        })
        valido, avisos = validar_timestamps_ordenados(df)
        assert valido is True
        assert len(avisos) == 0
    
    def test_timestamps_desorderados(self):
        """Timestamps fora de ordem."""
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 10, 1, 0, 0),
                datetime(2025, 10, 1, 2, 0),
                datetime(2025, 10, 1, 1, 0),  # ← Desordenado
            ],
            "postura": ["deitado"] * 3,
            "duracao_min": [60] * 3,
        })
        valido, avisos = validar_timestamps_ordenados(df)
        assert valido is False
        assert len(avisos) > 0
    
    def test_dataframe_vazio(self):
        """DataFrame vazio deve ser válido."""
        df = pd.DataFrame()
        valido, avisos = validar_timestamps_ordenados(df)
        assert valido is True


class TestValidarDuracoesPositivas:
    """Testes para validação de durações."""
    
    def test_duracoes_validas(self):
        """Todas as durações são positivas."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=3, freq="1h"),
            "duracao_min": [60, 45, 30],
        })
        valido, avisos = validar_duracoes_positivas(df)
        assert valido is True
        assert len(avisos) == 0
    
    def test_duracao_zero(self):
        """Durações com valor zero."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=3, freq="1h"),
            "duracao_min": [60, 0, 30],
        })
        valido, avisos = validar_duracoes_positivas(df)
        assert valido is False
        assert len(avisos) > 0
    
    def test_duracao_negativa(self):
        """Durações negativas."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=3, freq="1h"),
            "duracao_min": [60, -30, 30],
        })
        valido, avisos = validar_duracoes_positivas(df)
        assert valido is False
        assert len(avisos) > 0


class TestValidarPosturasValidas:
    """Testes para validação de posturas."""
    
    def test_posturas_validas(self):
        """Todas posturas são válidas."""
        df = pd.DataFrame({
            "postura": ["deitado", "sentado", "em_pe", "deitado"],
        })
        valido, avisos = validar_posturas_validas(df)
        assert valido is True
        assert len(avisos) == 0
    
    def test_postura_invalida(self):
        """Postura inválida."""
        df = pd.DataFrame({
            "postura": ["deitado", "flutuando", "em_pe"],  # ← Inválido
        })
        valido, avisos = validar_posturas_validas(df)
        assert valido is False
        assert len(avisos) > 0
    
    def test_multiplas_posturas_invalidas(self):
        """Múltiplas posturas inválidas."""
        df = pd.DataFrame({
            "postura": ["deitado", "voando", "flutuando"],
        })
        valido, avisos = validar_posturas_validas(df)
        assert valido is False


class TestValidarTransicoesValidas:
    """Testes para validação de transições."""
    
    def test_transicoes_validas(self):
        """Transições respeitam o grafo."""
        df = pd.DataFrame({
            "postura": ["deitado", "deitado", "sentado", "em_pe", "sentado", "deitado"],
        })
        valido, avisos = validar_transicoes_validas(df)
        assert valido is True
        assert len(avisos) == 0
    
    def test_transicao_invalida(self):
        """Transição inválida no grafo."""
        df = pd.DataFrame({
            "postura": ["deitado", "em_pe"],  # deitado não transita direto para em_pe
        })
        valido, avisos = validar_transicoes_validas(df)
        assert valido is False
        assert len(avisos) > 0
    
    def test_mesmo_postura_sempre_valido(self):
        """Ficar na mesma postura é sempre válido."""
        df = pd.DataFrame({
            "postura": ["sentado", "sentado", "sentado", "sentado"],
        })
        valido, avisos = validar_transicoes_validas(df)
        assert valido is True


class TestValidarCoberturaTemporal:
    """Testes para validação de cobertura temporal."""
    
    def test_cobertura_consistente(self):
        """Cobertura temporal consistente."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=24, freq="1h"),
            "duracao_min": [60] * 24,  # 24h * 60min = 1440min
        })
        valido, avisos = validar_cobertura_temporal(df)
        assert valido is True
    
    def test_cobertura_inconsistente(self):
        """Cobertura temporal inconsistente (fora de tolerância)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=10, freq="1h"),
            "duracao_min": [1] * 10,  # Apenas 10 minutos, não 10 horas
        })
        valido, avisos = validar_cobertura_temporal(df)
        # Deve retornar True mas com aviso (tolerância)
        assert valido is True
        assert len(avisos) > 0  # Deve ter aviso


class TestValidarSemDuplicatas:
    """Testes para validação de duplicatas."""
    
    def test_sem_duplicatas(self):
        """Sem registros duplicados."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=5, freq="1h"),
            "postura": ["deitado", "sentado", "em_pe", "sentado", "deitado"],
        })
        valido, avisos = validar_sem_duplicatas(df)
        assert valido is True
        assert len(avisos) == 0
    
    def test_com_duplicatas(self):
        """Com registros duplicados."""
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 10, 1, 0, 0),
                datetime(2025, 10, 1, 1, 0),
                datetime(2025, 10, 1, 0, 0),  # ← Duplicado
            ],
            "postura": ["deitado", "sentado", "deitado"],
        })
        valido, avisos = validar_sem_duplicatas(df)
        assert valido is False
        assert len(avisos) > 0


class TestValidarSessaoCompleta:
    """Testes de validação completa de sessão."""
    
    def test_sessao_valida(self):
        """Sessão completamente válida."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=24, freq="1h"),
            "postura": ["deitado", "sentado", "em_pe", "sentado"] * 6,
            "duracao_min": [60] * 24,
        })
        resultado = validar_sessao(df, verbose=False)
        assert resultado["valido"] is True
        assert resultado["timestamps_ordenados"] is True
        assert resultado["duracoes_positivas"] is True
        assert resultado["posturas_validas"] is True
        assert resultado["transicoes_validas"] is True
    
    def test_sessao_invalida_timestamps(self):
        """Sessão com timestamps fora de ordem."""
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 10, 1, 0, 0),
                datetime(2025, 10, 1, 2, 0),
                datetime(2025, 10, 1, 1, 0),  # ← Fora de ordem
            ],
            "postura": ["deitado", "sentado", "em_pe"],
            "duracao_min": [60, 60, 60],
        })
        resultado = validar_sessao(df, verbose=False)
        assert resultado["valido"] is False
        assert resultado["timestamps_ordenados"] is False
    
    def test_sessao_multiplos_erros(self):
        """Sessão com múltiplos erros."""
        df = pd.DataFrame({
            "timestamp": [
                datetime(2025, 10, 1, 0, 0),
                datetime(2025, 10, 1, 2, 0),
                datetime(2025, 10, 1, 1, 0),  # ← Fora de ordem
            ],
            "postura": ["deitado", "invalida", "em_pe"],  # ← Postura inválida
            "duracao_min": [60, -30, 60],  # ← Duração negativa
        })
        resultado = validar_sessao(df, verbose=False)
        assert resultado["valido"] is False
        # Múltiplos erros
        assert resultado["timestamps_ordenados"] is False
        assert resultado["posturas_validas"] is False
        assert resultado["duracoes_positivas"] is False
    
    def test_sessao_com_avisos(self):
        """Sessão válida mas com avisos."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=5, freq="1h"),
            "postura": ["deitado"] * 5,
            "duracao_min": [30, 30, 30, 30, 30],  # Menos que 5h
        })
        resultado = validar_sessao(df, verbose=False)
        # Deve ser válido (duração < tempo sim  ulado tem tolerância)
        assert resultado["valido"] is True
        assert len(resultado["avisos"]) > 0  # Mas com avisos


class TestCenariosClinicos:
    """Testes com cenários clínicos realistas."""
    
    def test_paciente_acamado(self):
        """Paciente acamado (sempre deitado)."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=24, freq="1h"),
            "postura": ["deitado"] * 24,
            "duracao_min": [60] * 24,
        })
        resultado = validar_sessao(df, verbose=False)
        assert resultado["valido"] is True
    
    def test_paciente_ambulatorio(self):
        """Paciente ambulatório (muitas transições)."""
        posturas = ["em_pe", "sentado", "em_pe", "sentado", "em_pe", "deitado", "sentado"] * 3 + ["em_pe"]
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=len(posturas), freq="1h"),
            "postura": posturas,
            "duracao_min": [60] * len(posturas),
        })
        resultado = validar_sessao(df, verbose=False)
        assert resultado["valido"] is True
    
    def test_paciente_com_queda_nocturna(self):
        """Paciente com transição rápida (simulando queda)."""
        # Caminho válido: deitado → sentado → em_pe → deitado (queda)
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-10-01", periods=10, freq="1h"),
            "postura": [
                "deitado",   # 0 - início acamado
                "sentado",   # 1 - levanta para sentar
                "em_pe",     # 2 - fica de pé
                "deitado",   # 3 - QUEDA RÁPIDA (em_pe → deitado)
                "deitado",   # 4
                "sentado",   # 5 - tenta sentar
                "em_pe",     # 6 - tenta ficar de pé novamente
                "sentado",   # 7 - volta a sentar
                "deitado",   # 8 - deita normalmente
                "deitado",   # 9 - descansa
            ],
            "duracao_min": [60] * 10,
        })
        resultado = validar_sessao(df, verbose=False)
        assert resultado["valido"] is True
        # Transição em_pe → deitado é válida no grafo


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
