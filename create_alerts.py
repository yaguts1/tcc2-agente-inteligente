#!/usr/bin/env python3
"""
Script para popular o banco com dados de teste realistas
Com padrões de postura que disparam alertas
"""
from datetime import datetime, timedelta
from interface.dao import inserir_timeline_event
import sqlite3

DB_PATH = 'tcc.db'

print("\n" + "="*60)
print("🔄 INSERINDO ALERTAS SIMULADOS")
print("="*60 + "\n")

# Get existing patients (read-only, close immediately)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
pacientes = c.execute("SELECT DISTINCT id FROM pacientes").fetchall()
pacientes = [p[0] for p in pacientes]
conn.close()

print(f"Encontrados {len(pacientes)} pacientes")

now = datetime.now()

# Insert alerts usando uma nova conexão (mais clean)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

for paciente_id in pacientes:
    print(f"\nGerando alertas para {paciente_id}...")
    
    # Generate 10-15 alerts for each patient
    num_alertas = 10 + (ord(paciente_id[-1]) % 5)
    for i in range(num_alertas):
        hours_back = (i + 1) * 2  # Every 2 hours
        inicio = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S")
        # Fim = inicio + 15 min (exemplo de duração)
        fim = (datetime.fromisoformat(inicio) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S")
        duracao_min = 15
        risco_level = ['baixo', 'médio', 'alto'][i % 3]
        
        # Insert alert record
        c.execute("""
            INSERT INTO alertas 
            (paciente_id, inicio, fim, tipo, perfil, janela_min, status, duracao_min) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paciente_id,
            inicio,
            fim,
            'imobilidade',
            risco_level,
            120,
            ['aberto', 'reconhecido', 'fechado'][i % 3],
            duracao_min
        ))
    
    print(f"  ✓ {num_alertas} alertas inseridos")

conn.commit()
conn.close()

# Insert timeline events - AGORA SIM, usar DAO sem competição de conexão
print("\nInserindo eventos de timeline...")
for paciente_id in pacientes:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    alertas = c.execute("SELECT inicio FROM alertas WHERE paciente_id = ?", (paciente_id,)).fetchall()
    conn.close()
    
    for idx, (inicio,) in enumerate(alertas):
        ts_ms = int(datetime.fromisoformat(inicio).timestamp() * 1000)
        tipo_evento = ['alert_open', 'alert_acknowledged', 'alert_completed'][idx % 3]
        
        inserir_timeline_event(
            DB_PATH,
            paciente_id,
            inicio,
            ts_ms,
            tipo_evento,
            descricao=f"Alerta de imobilidade - Risco automático"
        )

print("\n" + "="*60)
print("✅ ALERTAS E TIMELINE INSERIDOS COM SUCESSO")
print("="*60)

# Verify
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
alertas_count = c.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
timeline_count = c.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]
print(f"\nResumo:")
print(f"  • Alertas: {alertas_count}")
print(f"  • Timeline events: {timeline_count}")
print(f"  • Pacientes: {len(pacientes)}")
conn.close()

print("\nAgora você pode testar com dados realistas!\n")
