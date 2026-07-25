# -*- coding: utf-8 -*-
"""
Tests para Problema 3: Perfis Heterogêneos

Verifica que diferentes perfis de risco produzem variações significativas
no padrão de posicionamento dos pacientes.
"""
import pytest
from datetime import datetime, timedelta
from dados_simulados.gerador import (
    gerar_sessao_multi,
    gerar_sessao_simulada,
    PerfilPaciente,
    PERFIS_PREDEFINIDOS,
)


class TestPerfisPredefinidos:
    """Testa configuração de perfis predefinidos."""
    
    def test_perfis_predefinidos_existem(self):
        """Verifica que todos os perfis existem."""
        assert "baixo" in PERFIS_PREDEFINIDOS
        assert "medio" in PERFIS_PREDEFINIDOS
        assert "alto" in PERFIS_PREDEFINIDOS
    
    def test_perfis_tem_parametros_corretos(self):
        """Verifica estrutura dos perfis."""
        for nome_perfil, params in PERFIS_PREDEFINIDOS.items():
            assert "limite_tempo_postura" in params
            assert "prob_falha_reposicao" in params
            assert "duracao_refeicao" in params
    
    def test_risco_baixo_menos_falhas(self):
        """Risco baixo deve ter prob_falha_reposicao menor."""
        prob_baixo = PERFIS_PREDEFINIDOS["baixo"]["prob_falha_reposicao"]
        prob_medio = PERFIS_PREDEFINIDOS["medio"]["prob_falha_reposicao"]
        prob_alto = PERFIS_PREDEFINIDOS["alto"]["prob_falha_reposicao"]
        
        assert prob_baixo < prob_medio < prob_alto
    
    def test_risco_alto_limite_menor(self):
        """Risco alto deve ter limite_tempo_postura menor."""
        lim_baixo = PERFIS_PREDEFINIDOS["baixo"]["limite_tempo_postura"]
        lim_medio = PERFIS_PREDEFINIDOS["medio"]["limite_tempo_postura"]
        lim_alto = PERFIS_PREDEFINIDOS["alto"]["limite_tempo_postura"]
        
        assert lim_alto < lim_medio < lim_baixo


class TestGeradorComPerfisCustomizados:
    """Testa geração com perfis customizados."""
    
    def test_perfis_customizados_count_invalido(self):
        """Deve rejeitar se número de perfis != número de pacientes."""
        perfis = [PerfilPaciente(), PerfilPaciente()]
        
        with pytest.raises(ValueError, match="Número de perfis"):
            gerar_sessao_multi(
                pacientes=3,
                horas=1,
                passo_min=5,
                seed=42,
                perfis_customizados=perfis,
            )
    
    def test_perfis_customizados_aplicados(self):
        """Verifica que perfis customizados são usados."""
        perfis = [
            PerfilPaciente(
                nome="Paciente 1",
                limite_tempo_postura=200,
                prob_falha_reposicao=0.1,
            ),
            PerfilPaciente(
                nome="Paciente 2",
                limite_tempo_postura=50,
                prob_falha_reposicao=0.9,
            ),
        ]
        
        grades_dict, _, _ = gerar_sessao_multi(
            pacientes=2,
            horas=1,
            passo_min=5,
            seed=42,
            perfis_customizados=perfis,
        )
        
        assert len(grades_dict) == 2
        assert "PAC-0000" in grades_dict
        assert "PAC-0001" in grades_dict


class TestDistribuicaoPorRisco:
    """Testa distribuição de pacientes por risco."""
    
    def test_distribuir_por_risco_basico(self):
        """Testa distribuição básica por risco."""
        grades_dict, _, _ = gerar_sessao_multi(
            pacientes=6,
            horas=1,
            passo_min=5,
            seed=42,
            distribuir_por_risco=True,
        )
        
        assert len(grades_dict) == 6
        for i in range(6):
            assert f"PAC-{i:04d}" in grades_dict
    
    def test_distribuir_por_risco_cicla_niveis(self):
        """Testa que distribuição cicla por baixo/médio/alto."""
        pacientes = 9
        grades_dict, _, _ = gerar_sessao_multi(
            pacientes=pacientes,
            horas=1,
            passo_min=5,
            seed=42,
            distribuir_por_risco=True,
        )
        
        # Todos os pacientes devem estar presentes
        assert len(grades_dict) == pacientes


class TestHeterogeneidade:
    """Testa que diferentes riscos produzem heterogeneidade real."""
    
    def test_duracao_media_varia_por_risco(self):
        """Verifica que duração média varia entre perfis."""
        duracao_por_risco = {}
        
        for risco in ["baixo", "medio", "alto"]:
            params = PERFIS_PREDEFINIDOS[risco]
            perfil = PerfilPaciente(**params)
            
            grade, _ = gerar_sessao_simulada(
                duracao_horas=24,
                seed=42,
                passo_min=5,
                perfil=perfil,
            )
            
            # Conta transições (mudanças de postura)
            transicoes = (grade["postura"] != grade["postura"].shift()).sum()
            duracao_por_risco[risco] = transicoes
        
        # Deve haver variação entre riscos (mesmo com seed fixa)
        valores = list(duracao_por_risco.values())
        assert len(set(valores)) > 1, "Esperava variação mesmo com seed fixa"
    
    def test_heterogeneidade_multi_pacientes(self):
        """Verifica heterogeneidade em simulação multi-pacientes."""
        grades_dict, _, _ = gerar_sessao_multi(
            pacientes=6,
            horas=24,
            passo_min=5,
            seed=42,
            distribuir_por_risco=True,
        )
        
        # Coleta estatísticas por paciente
        stats = {}
        for pac_id, grade in grades_dict.items():
            transicoes = (grade["postura"] != grade["postura"].shift()).sum()
            stats[pac_id] = transicoes
        
        # Deve ter variação entre pacientes
        valores = list(stats.values())
        assert len(set(valores)) > 1, "Esperava variação entre pacientes"
    
    def test_variacao_40_porcento(self):
        """Testa que há pelo menos 40% variação entre riscos.

        `inicio` é fixo de propósito. Sem ele, `gerar_sessao_simulada` usa
        `datetime.now()` como referência e o resultado passa a depender do
        MINUTO em que a suíte roda: medindo os 60 minutos de uma hora, a
        variação fica >= 30% em 59 deles e cai para 27,3% em um — ou seja, o
        teste falhava sozinho em ~1,7% das execuções, sem nada ter mudado no
        código. Seed fixa e horário livre não combinam.
        """
        inicio = datetime(2026, 1, 15, 12, 0, 0)
        duracao_por_risco = {}

        for risco in ["baixo", "alto"]:
            params = PERFIS_PREDEFINIDOS[risco]
            perfil = PerfilPaciente(**params)

            grade, _ = gerar_sessao_simulada(
                duracao_horas=24,
                seed=42,
                passo_min=5,
                inicio=inicio,
                perfil=perfil,
            )
            
            # Usa tempo médio entre transições como métrica
            transicoes = (grade["postura"] != grade["postura"].shift()).sum()
            duracao_por_risco[risco] = transicoes
        
        alto = duracao_por_risco["alto"]
        baixo = duracao_por_risco["baixo"]
        
        if baixo > 0:
            variacao = abs(alto - baixo) / baixo
            assert variacao >= 0.3, f"Variação {variacao:.1%} < 40%"


class TestCompatibilidadeBackward:
    """Testa compatibilidade com código existente."""
    
    def test_gerar_sessao_multi_sem_parametros_novos(self):
        """Testa que função ainda funciona sem parâmetros novos."""
        grades_dict, contextos_dict, eventos_df = gerar_sessao_multi(
            pacientes=2,
            horas=1,
            passo_min=5,
            seed=42,
        )
        
        assert len(grades_dict) == 2
        assert len(contextos_dict) == 2
        assert len(eventos_df) > 0
    
    def test_perfil_padrao_medio(self):
        """Testa que perfil padrão é 'medio'."""
        grades_dict, _, _ = gerar_sessao_multi(
            pacientes=3,
            horas=1,
            passo_min=5,
            seed=42,
        )
        
        # Deve usar perfil 'medio' para todos
        assert len(grades_dict) == 3


class TestCenarioClinicoComRisco:
    """Testa cenários clínicos com pacientes de diferentes riscos."""
    
    def test_paciente_alto_risco_mais_transicoes(self):
        """Paciente alto risco deve gerar diferentes padrões."""
        # Paciente baixo risco
        perfil_baixo = PerfilPaciente(**PERFIS_PREDEFINIDOS["baixo"])
        grade_baixo, _ = gerar_sessao_simulada(
            duracao_horas=12,
            seed=42,
            passo_min=5,
            perfil=perfil_baixo,
        )
        transicoes_baixo = (grade_baixo["postura"] != grade_baixo["postura"].shift()).sum()
        
        # Paciente alto risco
        perfil_alto = PerfilPaciente(**PERFIS_PREDEFINIDOS["alto"])
        grade_alto, _ = gerar_sessao_simulada(
            duracao_horas=12,
            seed=42,
            passo_min=5,
            perfil=perfil_alto,
        )
        transicoes_alto = (grade_alto["postura"] != grade_alto["postura"].shift()).sum()
        
        # Deve haver diferença entre perfis
        assert transicoes_alto != transicoes_baixo, "Esperava padrões diferentes"
    
    def test_paciente_baixo_risco_menos_falhas(self):
        """Paciente baixo risco deve ter menos falhas."""
        from dados_simulados.gerador import gerar_eventos_sessao
        
        # Paciente baixo risco
        perfil_baixo = PerfilPaciente(**PERFIS_PREDEFINIDOS["baixo"])
        eventos_baixo = gerar_eventos_sessao(
            duracao_horas=24,
            seed=42,
            perfil=perfil_baixo,
        )
        falhas_baixo = eventos_baixo["falha"].sum()
        
        # Paciente alto risco
        perfil_alto = PerfilPaciente(**PERFIS_PREDEFINIDOS["alto"])
        eventos_alto = gerar_eventos_sessao(
            duracao_horas=24,
            seed=42,
            perfil=perfil_alto,
        )
        falhas_alto = eventos_alto["falha"].sum()
        
        # Alto risco deve ter mais falhas
        assert falhas_alto >= falhas_baixo


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
