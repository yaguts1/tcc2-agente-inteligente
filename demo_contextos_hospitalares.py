#!/usr/bin/env python
# -- coding: utf-8 --
# demo_contextos_hospitalares.py
"""
Demonstração Prática: Contextos Hospitalares (Problema 1)

Este script mostra como a implementação resolve o problema original:
- Antes: Sistema marca alerta mesmo durante refeição/cirurgia
- Depois: Sistema conhece eventos agendados e suprime falsos positivos
"""

from datetime import datetime
from dados_simulados.gerador import gerar_sessao_simulada, gerar_sessao_multi
from dados_simulados.contextos import resumir_contextos, filtrar_alertas_por_contexto
import pandas as pd


def demo_1_basica():
    """Demonstração 1: Uso básico com contextos."""
    print("\n" + "="*80)
    print("DEMO 1: Geração Básica com Contextos Hospitalares")
    print("="*80)
    
    # Gera sessão
    print("\n📊 Gerando sessão de 24 horas com contextos...")
    grade, contextos = gerar_sessao_simulada(
        duracao_horas=24,
        seed=42,
        passo_min=5,
        incluir_contexto=True,
    )
    
    print(f"\n✅ Gerado com sucesso!")
    print(f"   - Registros na grade: {len(grade)}")
    print(f"   - Eventos contextuais: {len(contextos)}")
    
    # Mostra resumo de contextos
    print("\n📋 Eventos Agendados:")
    print(resumir_contextos(contextos))
    
    # Analisa distribuição de contextos
    print("\n📊 Distribuição de Contextos na Grade:")
    context_counts = grade["contexto"].value_counts()
    for ctx, count in context_counts.items():
        pct = 100 * count / len(grade)
        print(f"   {ctx:20s}: {count:4d} registros ({pct:5.1f}%)")
    
    print(f"   {'Sem contexto':20s}: {grade['contexto'].isna().sum():4d} registros "
          f"({100*grade['contexto'].isna().sum()/len(grade):5.1f}%)")
    
    # Mostra amostra de dados
    print("\n🔍 Amostra de dados (6:00-6:35):")
    inicio_refeicao = pd.to_datetime("2025-10-27T06:00:00")
    fim_refeicao = pd.to_datetime("2025-10-27T06:35:00")
    
    mask = (pd.to_datetime(grade["timestamp"]) >= inicio_refeicao) & \
           (pd.to_datetime(grade["timestamp"]) <= fim_refeicao)
    amostra = grade[mask][["timestamp", "postura", "contexto", "suprime_alerta"]]
    
    print(amostra.to_string(index=False))


def demo_2_sem_contexto():
    """Demonstração 2: Comparação com e sem contexto."""
    print("\n" + "="*80)
    print("DEMO 2: Comparação - COM vs SEM Contextos")
    print("="*80)
    
    # Gera SEM contexto
    print("\n📊 Gerando sessão SEM contextos...")
    grade_sem, contextos_sem = gerar_sessao_simulada(
        duracao_horas=24,
        seed=42,
        passo_min=5,
        incluir_contexto=False,
    )
    
    # Gera COM contexto
    print("📊 Gerando sessão COM contextos (mesmo seed)...")
    grade_com, contextos_com = gerar_sessao_simulada(
        duracao_horas=24,
        seed=42,
        passo_min=5,
        incluir_contexto=True,
    )
    
    print("\n✅ Comparação:")
    print(f"\nSEM contexto:")
    print(f"   - Colunas: {list(grade_sem.columns)}")
    print(f"   - Eventos contextuais: {len(contextos_sem)}")
    print(f"   - Suprime_alerta (SIM): {grade_sem['suprime_alerta'].sum()}")
    
    print(f"\nCOM contexto:")
    print(f"   - Colunas: {list(grade_com.columns)}")
    print(f"   - Eventos contextuais: {len(contextos_com)}")
    print(f"   - Suprime_alerta (SIM): {grade_com['suprime_alerta'].sum()}")
    
    # Verifica que dados de postura são iguais (contexto não muda movimento)
    posturas_iguais = (grade_sem["postura"].values == grade_com["postura"].values).all()
    print(f"\n✅ Dados de postura idênticos: {posturas_iguais}")


def demo_3_cenario_refeicao():
    """Demonstração 3: Cenário clínico - Paciente em refeição."""
    print("\n" + "="*80)
    print("DEMO 3: Cenário Clínico - Detecção de Alerta Durante Refeição")
    print("="*80)
    
    grade, contextos = gerar_sessao_simulada(
        duracao_horas=24,
        seed=42,
        passo_min=5,
        incluir_contexto=True,
    )
    
    # Encontra primeira refeição
    refeicoes = [c for c in contextos if c.tipo == "refeicao"]
    if refeicoes:
        refeicao = refeicoes[0]
        print(f"\n🍽️  Refeição encontrada:")
        print(f"   Início: {refeicao.inicio.strftime('%H:%M:%S')}")
        print(f"   Fim:    {refeicao.fim.strftime('%H:%M:%S')}")
        print(f"   Duração: {refeicao.duracao_min:.0f} minutos")
        print(f"   Suprime alerta: {refeicao.suprime_alerta}")
        
        # Dados durante refeição
        mask = (pd.to_datetime(grade["timestamp"]) >= refeicao.inicio) & \
               (pd.to_datetime(grade["timestamp"]) <= refeicao.fim)
        grade_refeicao = grade[mask]
        
        print(f"\n📊 Dados durante refeição:")
        print(f"   Registros: {len(grade_refeicao)}")
        print(f"   Posturas únicas: {grade_refeicao['postura'].unique()}")
        print(f"   Contexto marcado: {grade_refeicao['contexto'].unique()[0]}")
        print(f"   Todos com suprime_alerta=True: {grade_refeicao['suprime_alerta'].all()}")
        
        print(f"\n✅ Conclusão:")
        print(f"   Mesmo que paciente fique em supino por {refeicao.duracao_min:.0f}min,")
        print(f"   o sistema NÃO gerará alerta (contexto clínico legítimo)")


def demo_4_cenario_cirurgia():
    """Demonstração 4: Cenário clínico - Cirurgia agendada."""
    print("\n" + "="*80)
    print("DEMO 4: Cenário Clínico - Cirurgia Agendada")
    print("="*80)
    
    tipos_eventos = {
        "refeicao": False,
        "higiene": False,
        "medicacao": False,
        "cirurgia": True,  # Inclui cirurgia
        "visita": False,
        "avaliacao_medica": False,
    }
    
    # Tenta vários seeds até encontrar cirurgia
    print("\n🔍 Procurando por cirurgia agendada...")
    cirurgia_encontrada = None
    
    for seed in range(100):
        grade, contextos = gerar_sessao_simulada(
            duracao_horas=24,
            seed=seed,
            passo_min=5,
            incluir_contexto=True,
            tipos_eventos=tipos_eventos,
        )
        
        cirurgias = [c for c in contextos if c.tipo == "cirurgia"]
        if cirurgias:
            cirurgia_encontrada = cirurgias[0]
            grade_cirurgia = grade
            break
    
    if cirurgia_encontrada:
        print(f"✅ Cirurgia encontrada (seed={seed}):")
        print(f"   Início: {cirurgia_encontrada.inicio.strftime('%H:%M:%S')}")
        print(f"   Fim:    {cirurgia_encontrada.fim.strftime('%H:%M:%S')}")
        print(f"   Duração: {cirurgia_encontrada.duracao_min:.0f} minutos")
        
        # Dados durante cirurgia
        mask = (pd.to_datetime(grade_cirurgia["timestamp"]) >= cirurgia_encontrada.inicio) & \
               (pd.to_datetime(grade_cirurgia["timestamp"]) <= cirurgia_encontrada.fim)
        grade_cirurgia = grade_cirurgia[mask]
        
        print(f"\n📊 Dados durante cirurgia:")
        print(f"   Registros: {len(grade_cirurgia)}")
        print(f"   Contexto marcado: {grade_cirurgia['contexto'].unique()[0]}")
        print(f"   Todos com suprime_alerta=True: {grade_cirurgia['suprime_alerta'].all()}")
        
        print(f"\n✅ Conclusão:")
        print(f"   Paciente em cirurgia - imobilidade é ESPERADA")
        print(f"   Sistema suprime alerta automaticamente")
    else:
        print("⚠️  Cirurgia não encontrada nos 100 seeds testados")


def demo_5_filtro_alertas():
    """Demonstração 5: Filtro de alertas por contexto."""
    print("\n" + "="*80)
    print("DEMO 5: Filtro de Alertas - Evitando Falsos Positivos")
    print("="*80)
    
    grade, contextos = gerar_sessao_simulada(
        duracao_horas=24,
        seed=42,
        passo_min=5,
        incluir_contexto=True,
    )
    
    # Simula alertas: a cada 60 minutos em supino
    alertas_simulados = []
    for i, (_, row) in enumerate(grade.iterrows()):
        if row["postura"] == "supino" and i % 12 == 0:  # A cada 60 min (12 * 5min)
            alertas_simulados.append({
                "timestamp": row["timestamp"],
                "postura": row["postura"],
            })
    
    print(f"\n🚨 Alertas Simulados (sem considerar contexto):")
    print(f"   Total: {len(alertas_simulados)} alertas")
    
    # Filtra por contexto
    alertas_validos, alertas_suprimidos = filtrar_alertas_por_contexto(
        alertas_simulados,
        contextos
    )
    
    print(f"\n✅ Após filtragem por contexto:")
    print(f"   Alertas válidos (risco real): {len(alertas_validos)}")
    print(f"   Alertas suprimidos (contexto clínico): {len(alertas_suprimidos)}")
    
    taxa_reducao = 100 * len(alertas_suprimidos) / (len(alertas_simulados) + 0.001)
    print(f"   Taxa de redução de falsos positivos: {taxa_reducao:.1f}%")
    
    print(f"\n📊 Detalhes dos alertas suprimidos:")
    tipos_suprimidos = {}
    for alerta in alertas_suprimidos:
        ctx = alerta.get("contexto_suprimido", "desconhecido")
        tipos_suprimidos[ctx] = tipos_suprimidos.get(ctx, 0) + 1
    
    for ctx, count in sorted(tipos_suprimidos.items()):
        print(f"   {ctx:20s}: {count} alertas evitados")


def demo_6_multi_pacientes():
    """Demonstração 6: Múltiplos pacientes com contextos."""
    print("\n" + "="*80)
    print("DEMO 6: Múltiplos Pacientes com Contextos")
    print("="*80)
    
    print("\n👥 Gerando 3 pacientes com contextos...")
    grades_dict, contextos_dict, eventos_df = gerar_sessao_multi(
        pacientes=3,
        horas=24,
        passo_min=5,
        seed=42,
        incluir_contexto=True,
    )
    
    print(f"\n✅ Gerado com sucesso!")
    print(f"   Pacientes: {len(grades_dict)}")
    
    for pac_id, grade in grades_dict.items():
        contextos = contextos_dict[pac_id]
        suprimidos = grade["suprime_alerta"].sum()
        total = len(grade)
        
        print(f"\n{pac_id}:")
        print(f"   Registros: {total}")
        print(f"   Contextos agendados: {len(contextos)}")
        print(f"   Timestamps com suprime_alerta: {suprimidos} ({100*suprimidos/total:.1f}%)")
        
        # Tipos de contexto
        tipos = {}
        for ctx in contextos:
            tipos[ctx.tipo] = tipos.get(ctx.tipo, 0) + 1
        
        print(f"   Tipos de eventos:")
        for tipo, count in sorted(tipos.items()):
            print(f"      - {tipo}: {count}")


def demo_7_resumo_comparativo():
    """Demonstração 7: Resumo comparativo antes/depois."""
    print("\n" + "="*80)
    print("DEMO 7: Resumo - ANTES vs DEPOIS")
    print("="*80)
    
    print("\n❌ ANTES (Problema 1 Original):")
    print("""
    Sistema ignora eventos agendados
    
    Exemplo: Paciente em refeição às 6:00-6:30
    - Sistema vê: Supino por 30 minutos
    - Sistema gera: ALERTA (imobilidade prolongada)
    - Clínico vê: Alerta sem contexto
    - Resultado: FALSO POSITIVO
    
    Impacto:
    ❌ Reduz confiança no sistema
    ❌ Aumenta carga de trabalho (alertas desnecessários)
    ❌ Impossível auditar: "por que foi alerta?"
    ❌ Clinicamente indefensável
    """)
    
    print("\n✅ DEPOIS (Problema 1 Resolvido):")
    print("""
    Sistema conhece eventos agendados
    
    Exemplo: Paciente em refeição às 6:00-6:30
    - Sistema vê: Supino por 30 minutos
    - Sistema sabe: Contexto = refeição
    - Sistema marca: suprime_alerta = True
    - Sistema NÃO gera: ALERTA
    - Clínico vê: Sem falso alerta
    - Resultado: ZERO FALSOS POSITIVOS
    
    Impacto:
    ✅ Aumenta confiança no sistema
    ✅ Reduz carga de trabalho
    ✅ Auditoria clara: "Estava em refeição"
    ✅ Clinicamente defensável para defesa
    """)


if __name__ == "__main__":
    print("\n" + "🏥"*40)
    print("DEMONSTRAÇÃO: PROBLEMA 1 - CONTEXTOS HOSPITALARES")
    print("🏥"*40)
    
    # Executa todas as demos
    demo_1_basica()
    demo_2_sem_contexto()
    demo_3_cenario_refeicao()
    demo_4_cenario_cirurgia()
    demo_5_filtro_alertas()
    demo_6_multi_pacientes()
    demo_7_resumo_comparativo()
    
    print("\n" + "="*80)
    print("✅ DEMONSTRAÇÃO COMPLETA")
    print("="*80)
    print("\n📚 Próximas melhorias:")
    print("   1. Problema 3 - Perfis Heterogêneos")
    print("   2. Problema 6 - Validação de Dados")
    print("   3. Problema 2 - Grade Discretização")
    print("\n")
