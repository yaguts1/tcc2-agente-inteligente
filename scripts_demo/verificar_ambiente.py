"""Verificação final do ambiente de demonstração."""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Estatísticas
cursor.execute('''
    SELECT p.id, f.cama_id 
    FROM pacientes p 
    LEFT JOIN paciente_fichas f ON p.id = f.paciente_id 
    WHERE p.id LIKE "DEMO-%"
''')
pacientes_demo = cursor.fetchall()

limite_24h = (datetime.now() - timedelta(hours=24)).isoformat()
cursor.execute('SELECT COUNT(*) FROM alertas WHERE paciente_id LIKE "DEMO-%" AND inicio >= ?', (limite_24h,))
alertas_24h = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM device_events WHERE processed_at IS NULL')
orfaos = cursor.fetchone()[0]

print(f'\n  📊 RESUMO DO AMBIENTE:')
print(f'  ─────────────────────────────────')
print(f'  Pacientes de demo: {len(pacientes_demo)}')
for pac_id, cama_id in pacientes_demo:
    leito = cama_id if cama_id else '(sem leito)'
    print(f'    • {pac_id} - Leito: {leito}')

print(f'\n  Alertas (últimas 24h): {alertas_24h}')
print(f'  Eventos órfãos: {orfaos}')
print(f'  ─────────────────────────────────')

conn.close()
