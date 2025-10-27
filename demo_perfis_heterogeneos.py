# -*- coding: utf-8 -*-
"""
Demo: Problema 3 - Perfis Heterogêneos

Demonstra como diferentes perfis de risco geram padrões de posicionamento distintos.
"""
import pandas as pd
from datetime import datetime
from dados_simulados.gerador import (
    gerar_sessao_multi,
    gerar_sessao_simulada,
    PerfilPaciente,
    PERFIS_PREDEFINIDOS,
)


def demo_1_perfis_predefinidos():
    """Demo 1: Visualiza os perfis predefinidos."""
    print("\n" + "="*70)
    print("DEMO 1: Perfis Predefinidos (Baixo/Médio/Alto Risco)")
    print("="*70)
    
    for risco, params in PERFIS_PREDEFINIDOS.items():
        print(f"\n  {risco.upper()}:")
        for chave, valor in params.items():
            print(f"    - {chave}: {valor}")


def demo_2_comparar_riscos():
    """Demo 2: Compara estatísticas entre perfis."""
    print("\n" + "="*70)
    print("DEMO 2: Comparação de Estatísticas por Risco")
    print("="*70)
    
    stats = {}
    
    for risco in ["baixo", "medio", "alto"]:
        params = PERFIS_PREDEFINIDOS[risco]
        perfil = PerfilPaciente(**params)
        
        grade, _ = gerar_sessao_simulada(
            duracao_horas=24,
            seed=42,
            passo_min=5,
            perfil=perfil,
        )
        
        # Calcula estatísticas
        transicoes = (grade["postura"] != grade["postura"].shift()).sum()
        postura_mais_comum = grade["postura"].mode()[0]
        
        stats[risco] = {
            "transicoes": transicoes,
            "postura_comum": postura_mais_comum,
            "amostras": len(grade),
        }
    
    print("\n  Comparação (24 horas de simulação):")
    df_stats = pd.DataFrame(stats).T
    print(df_stats.to_string())


def demo_3_perfis_customizados():
    """Demo 3: Cria perfis customizados."""
    print("\n" + "="*70)
    print("DEMO 3: Perfis Customizados")
    print("="*70)
    
    # Define pacientes específicos
    perfis = [
        PerfilPaciente(
            nome="Maria (Baixo Risco)",
            limite_tempo_postura=180,
            prob_falha_reposicao=0.2,
        ),
        PerfilPaciente(
            nome="João (Alto Risco)",
            limite_tempo_postura=60,
            prob_falha_reposicao=0.95,
        ),
    ]
    
    grades_dict, _, _ = gerar_sessao_multi(
        pacientes=2,
        horas=12,
        passo_min=5,
        seed=42,
        perfis_customizados=perfis,
    )
    
    for pac_id, grade in grades_dict.items():
        transicoes = (grade["postura"] != grade["postura"].shift()).sum()
        print(f"\n  Paciente {pac_id}: {transicoes} transições")


def demo_4_distribuicao_por_risco():
    """Demo 4: Distribui pacientes por risco automaticamente."""
    print("\n" + "="*70)
    print("DEMO 4: Distribuição Automática por Risco (6 pacientes)")
    print("="*70)
    
    grades_dict, _, _ = gerar_sessao_multi(
        pacientes=6,
        horas=24,
        passo_min=5,
        seed=42,
        distribuir_por_risco=True,
    )
    
    print("\n  Padrão de distribuição: BAIXO, MÉDIO, ALTO, BAIXO, MÉDIO, ALTO")
    print("\n  Estatísticas por paciente:")
    
    for idx, (pac_id, grade) in enumerate(grades_dict.items()):
        transicoes = (grade["postura"] != grade["postura"].shift()).sum()
        risco = ["BAIXO", "MÉDIO", "ALTO"][idx % 3]
        print(f"    {pac_id}: {transicoes:2d} transições ({risco})")


def demo_5_heterogeneidade_global():
    """Demo 5: Mostra heterogeneidade em simulação multi-pacientes."""
    print("\n" + "="*70)
    print("DEMO 5: Heterogeneidade em Simulação Multi-Pacientes")
    print("="*70)
    
    # SEM heterogeneidade (todos com mesmo perfil)
    grades_dict_uniforme, _, _ = gerar_sessao_multi(
        pacientes=6,
        horas=24,
        passo_min=5,
        seed=42,
        distribuir_por_risco=False,
    )
    
    # COM heterogeneidade (riscos diferentes)
    grades_dict_hetero, _, _ = gerar_sessao_multi(
        pacientes=6,
        horas=24,
        passo_min=5,
        seed=42,
        distribuir_por_risco=True,
    )
    
    print("\n  Sem Heterogeneidade (todos 'médio'):")
    transicoes_uniforme = []
    for grade in grades_dict_uniforme.values():
        transicoes = (grade["postura"] != grade["postura"].shift()).sum()
        transicoes_uniforme.append(transicoes)
    print(f"    Min: {min(transicoes_uniforme)}, Max: {max(transicoes_uniforme)}, "
          f"Variação: {max(transicoes_uniforme) - min(transicoes_uniforme)}")
    
    print("\n  Com Heterogeneidade (baixo/médio/alto):")
    transicoes_hetero = []
    for grade in grades_dict_hetero.values():
        transicoes = (grade["postura"] != grade["postura"].shift()).sum()
        transicoes_hetero.append(transicoes)
    print(f"    Min: {min(transicoes_hetero)}, Max: {max(transicoes_hetero)}, "
          f"Variação: {max(transicoes_hetero) - min(transicoes_hetero)}")


def demo_6_cenario_clinico_realista():
    """Demo 6: Cenário clínico com diferentes riscos."""
    print("\n" + "="*70)
    print("DEMO 6: Cenário Clínico Realista")
    print("="*70)
    
    # Cria coorte realista: 3 baixo risco, 3 médio, 2 alto
    perfis = [
        # Baixo risco (mobilidade boa)
        PerfilPaciente(
            nome="José (Baixo - Fractura antiga)",
            limite_tempo_postura=200,
            prob_falha_reposicao=0.2,
        ),
        PerfilPaciente(
            nome="Ana (Baixo - Recuperação cirúrgica)",
            limite_tempo_postura=190,
            prob_falha_reposicao=0.3,
        ),
        PerfilPaciente(
            nome="Carlos (Baixo - Mobilidade normal)",
            limite_tempo_postura=210,
            prob_falha_reposicao=0.15,
        ),
        # Médio risco (mobilidade reduzida)
        PerfilPaciente(
            nome="Maria (Médio - Artrose)",
            limite_tempo_postura=120,
            prob_falha_reposicao=0.7,
        ),
        PerfilPaciente(
            nome="Pedro (Médio - Obesidade)",
            limite_tempo_postura=130,
            prob_falha_reposicao=0.65,
        ),
        PerfilPaciente(
            nome="Rosa (Médio - Trauma agudo)",
            limite_tempo_postura=110,
            prob_falha_reposicao=0.75,
        ),
        # Alto risco (repouso obrigatório)
        PerfilPaciente(
            nome="João (Alto - Pós-cirúrgico)",
            limite_tempo_postura=60,
            prob_falha_reposicao=0.95,
        ),
        PerfilPaciente(
            nome="Lucia (Alto - Parkinson)",
            limite_tempo_postura=50,
            prob_falha_reposicao=0.98,
        ),
    ]
    
    from dados_simulados.gerador import gerar_eventos_sessao
    
    print("\n  Análise de Risco (evento por paciente):")
    for perfil in perfis:
        eventos = gerar_eventos_sessao(
            duracao_horas=24,
            seed=42,
            perfil=perfil,
        )
        falhas = eventos["falha"].sum()
        print(f"    {perfil.nome}: {falhas} falhas em repouso")


def demo_7_metricas_heterogeneidade():
    """Demo 7: Calcula métricas de heterogeneidade."""
    print("\n" + "="*70)
    print("DEMO 7: Métricas de Heterogeneidade")
    print("="*70)
    
    grades_dict, _, _ = gerar_sessao_multi(
        pacientes=12,
        horas=24,
        passo_min=5,
        seed=42,
        distribuir_por_risco=True,
    )
    
    transicoes_lista = []
    for grade in grades_dict.values():
        transicoes = (grade["postura"] != grade["postura"].shift()).sum()
        transicoes_lista.append(int(transicoes))  # Converte para int puro
    
    import statistics
    media = statistics.mean(transicoes_lista)
    desvio = statistics.stdev(transicoes_lista)
    coef_var = (desvio / media) * 100 if media > 0 else 0
    
    print(f"\n  Estatísticas de Transições:")
    print(f"    Média: {media:.1f}")
    print(f"    Desvio Padrão: {desvio:.1f}")
    print(f"    Coeficiente de Variação: {coef_var:.1f}%")
    print(f"    Min: {min(transicoes_lista)}")
    print(f"    Max: {max(transicoes_lista)}")
    print(f"    Range: {max(transicoes_lista) - min(transicoes_lista)}")
    
    if coef_var >= 30:
        print(f"\n    ✓ Heterogeneidade EXCELENTE (CoV ≥ 30%)")
    elif coef_var >= 20:
        print(f"\n    ✓ Heterogeneidade BOA (CoV ≥ 20%)")
    else:
        print(f"\n    ⚠ Heterogeneidade BAIXA (CoV < 20%)")


if __name__ == "__main__":
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + " PROBLEMA 3: PERFIS HETEROGÊNEOS - DEMONSTRAÇÕES ".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    demo_1_perfis_predefinidos()
    demo_2_comparar_riscos()
    demo_3_perfis_customizados()
    demo_4_distribuicao_por_risco()
    demo_5_heterogeneidade_global()
    demo_6_cenario_clinico_realista()
    demo_7_metricas_heterogeneidade()
    
    print("\n" + "█"*70)
    print("█" + " Demos Concluídas! ".center(68) + "█")
    print("█"*70 + "\n")
