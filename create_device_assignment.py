import sqlite3
from datetime import datetime

conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Verificar assignments
print('Device Assignments:')
cursor.execute("SELECT * FROM device_assignments")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row}')
else:
    print('  ❌ Nenhuma associação device→paciente!')

# Verificar schema de devices
print('\nSchema de devices:')
cursor.execute("PRAGMA table_info(devices)")
for row in cursor.fetchall():
    print(f'  {row}')

# Verificar schema de device_assignments  
print('\nSchema de device_assignments:')
cursor.execute("PRAGMA table_info(device_assignments)")
for row in cursor.fetchall():
    print(f'  {row}')

# Criar assignment para o teste (ajustado para schema correto)
print('\nCriando assignment DEV-TEST-001 → PAC-0001...')
now = datetime.now().isoformat()
now_ms = int(datetime.now().timestamp() * 1000)

try:
    # Criar assignment diretamente com schema correto
    cursor.execute("""
        INSERT OR REPLACE INTO device_assignments 
        (device_id, paciente_id, cama_id, start_ts, start_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('DEV-TEST-001', 'PAC-0001', 'C-01', now, now_ms, now))
    
    conn.commit()
    print('✅ Assignment criado!')
    
    # Verificar
    cursor.execute("SELECT * FROM device_assignments WHERE device_id = 'DEV-TEST-001'")
    row = cursor.fetchone()
    print(f'\nAssignment ativo:')
    print(f'  Device: {row[1]}, Paciente: {row[3]}, Cama: {row[2]}, Início: {row[4]}')
    
except Exception as e:
    print(f'❌ Erro: {e}')
    import traceback
    traceback.print_exc()

conn.close()
