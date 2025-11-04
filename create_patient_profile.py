import sqlite3
import json
from datetime import datetime

conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Verificar schema de paciente_fichas
print('Schema de paciente_fichas:')
cursor.execute("PRAGMA table_info(paciente_fichas)")
for row in cursor.fetchall():
    print(f'  {row}')

# Criar ficha para PAC-0001 com perfil ALTO
print('\nCriando ficha para PAC-0001...')

now = datetime.now().isoformat()

try:
    cursor.execute("""
        INSERT OR REPLACE INTO paciente_fichas 
        (paciente_id, nome, perfil, cama_id, observacoes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        'PAC-0001',
        'Paciente Teste WebSocket',
        'alto',  # IMPORTANTE: perfil alto para gerar alertas rapidamente
        'C-01',
        'Paciente de teste para validação do sistema WebSocket em tempo real',
        now,
        now
    ))
    
    conn.commit()
    print('✅ Ficha criada com sucesso!')
    
    # Verificar
    cursor.execute("SELECT * FROM paciente_fichas WHERE paciente_id = 'PAC-0001'")
    row = cursor.fetchone()
    print(f'\nFicha cadastrada:')
    print(f'  Paciente ID: {row[0]}')
    print(f'  Nome: {row[1]}')
    print(f'  Perfil: {row[2]}')
    print(f'  Cama: {row[3]}')
    
except Exception as e:
    print(f'❌ Erro: {e}')

conn.close()
