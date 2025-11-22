"""Limpa dados antigos de demonstração."""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Remover pacientes de demo anteriores
cursor.execute('DELETE FROM alertas WHERE paciente_id LIKE "DEMO-%"')
cursor.execute('DELETE FROM grade WHERE paciente_id LIKE "DEMO-%"')
cursor.execute('DELETE FROM paciente_fichas WHERE paciente_id LIKE "DEMO-%"')
cursor.execute('DELETE FROM pacientes WHERE id LIKE "DEMO-%"')

# Limpar eventos órfãos antigos (> 7 dias)
limite = (datetime.now() - timedelta(days=7)).isoformat()
cursor.execute('DELETE FROM device_events WHERE ts < ?', (limite,))

conn.commit()

# Estatísticas
cursor.execute('SELECT COUNT(*) FROM pacientes')
total_pacientes = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM alertas')
total_alertas = cursor.fetchone()[0]

print(f'  ✓ Banco limpo')
print(f'  → Pacientes restantes: {total_pacientes}')
print(f'  → Alertas restantes: {total_alertas}')

conn.close()
