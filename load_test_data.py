#!/usr/bin/env python3
"""
Script para popular o banco com dados de teste
Simula pacientes e alertas para validação do sistema
"""
import pandas as pd
from datetime import datetime, timedelta
from interface.dao import (
    criar_esquema,
    inserir_grade,
    inserir_eventos,
    inserir_alertas,
    inserir_timeline_event,
    criar_usuario
)
from modulo_alerta.engine import processar_alertas

DB_PATH = 'tcc.db'

print("\n" + "="*60)
print("🔄 POPULANDO BANCO COM DADOS DE TESTE")
print("="*60 + "\n")

# 1. Create schema
print("1. Criando schema...")
criar_esquema(DB_PATH)
print("   ✓ Schema criado")

# 2. Create test user
print("\n2. Criando usuário de teste...")
try:
    criar_usuario(DB_PATH, "admin", "admin123", "Administrador")
    print("   ✓ Usuário criado: admin/admin123")
except:
    print("   ✓ Usuário já existe")

# 3. Create test data
print("\n3. Criando dados simulados...")

pacientes = [
    "PAC-0001", "PAC-0002", "PAC-0003", 
    "PAC-0004", "PAC-0005"
]

posturas = ['Supino', 'Lateral D', 'Lateral E', 'Sentado', 'Fowler']
now = datetime.now()

# Generate 10 hours of simulated data for each patient
for paciente_id in pacientes:
    print(f"\n   Gerando dados para {paciente_id}...")
    
    grades = []
    eventos = []
    
    # Generate hourly data for last 24 hours
    for hours_back in range(24, 0, -1):
        timestamp = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S")
        postura = posturas[hours_back % len(posturas)]
        
        grade_row = {
            'timestamp': timestamp,
            'paciente_id': paciente_id,
            'postura': postura,
            'sala': f"Sala {paciente_id[-2:]}",
            'cama': int(paciente_id[-4:]) % 10 + 1
        }
        grades.append(grade_row)
    
    # Insert grade
    df_grade = pd.DataFrame(grades)
    inserir_grade(DB_PATH, df_grade, paciente_id)
    
    # Process alerts
    _, alertas = processar_alertas(df_grade[['timestamp', 'postura']], 'medio', paciente_id)
    
    if alertas:
        print(f"      ✓ {len(grades)} eventos, {len(alertas)} alertas")
        inserir_alertas(DB_PATH, alertas, paciente_id)
        
        # Add timeline events
        for alert in alertas[:3]:  # Sample timeline events
            inserir_timeline_event(
                DB_PATH,
                paciente_id,
                alert.get('ts', now.strftime("%Y-%m-%dT%H:%M:%S")),
                int(datetime.fromisoformat(alert.get('ts', now.strftime("%Y-%m-%dT%H:%M:%S"))).timestamp() * 1000),
                'alert_open',
                descricao=f"Alerta de reposicionamento - Risco {alert.get('risco', 'desconhecido')}"
            )
        print(f"      ✓ Timeline events adicionados")
    else:
        print(f"      ✓ {len(grades)} eventos (sem alertas)")

print("\n" + "="*60)
print("✅ DADOS DE TESTE CARREGADOS COM SUCESSO")
print("="*60)
print("\nAgora você pode:")
print("  1. Abrir http://localhost:3000")
print("  2. Fazer login com: admin / admin123")
print("  3. Ver alertas no Dashboard")
print("  4. Navegar para Timeline/Histórico")
print("\n")
