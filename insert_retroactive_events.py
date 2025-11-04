import sqlite3
from datetime import datetime, timedelta
import json

conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Inserir eventos retroativos simulando 65 minutos na mesma postura
# Isso DEVE gerar alerta para perfil ALTO (janela = 60min)

paciente_id = 'PAC-0001'
device_id = 'DEV-TEST-001'
postura = 'decubito_dorsal'

# Criar eventos a cada 5 minutos nas últimas 65 minutos
now = datetime.now()
eventos = []

print('Criando eventos retroativos...')
for i in range(13):  # 13 eventos x 5min = 65 minutos
    timestamp = now - timedelta(minutes=65 - (i * 5))
    ts_iso = timestamp.strftime("%Y-%m-%dT%H:%M:%S")
    
    eventos.append({
        "paciente_id": paciente_id,
        "inicio": ts_iso,
        "fim": None,
        "tipo": "sensor"
    })
    
    print(f'  {i+1}. {ts_iso} - {postura}')

# Inserir no banco
try:
    for evt in eventos:
        cursor.execute("""
            INSERT INTO eventos (paciente_id, inicio, fim, tipo)
            VALUES (?, ?, ?, ?)
        """, (evt["paciente_id"], evt["inicio"], evt["fim"], evt["tipo"]))
    
    conn.commit()
    print(f'\n✅ {len(eventos)} eventos inseridos!')
    
    # Verificar
    cursor.execute("""
        SELECT COUNT(*) FROM eventos 
        WHERE paciente_id = ? AND inicio > ?
    """, (paciente_id, (now - timedelta(hours=2)).isoformat()))
    
    count = cursor.fetchone()[0]
    print(f'Total de eventos recentes de {paciente_id}: {count}')
    
except Exception as e:
    print(f'❌ Erro: {e}')
    import traceback
    traceback.print_exc()

conn.close()

print('\n✅ Pronto! Agora processe os alertas com:')
print('   python -c "from servicos.processamento_incremental import ProcessadorIncremental; p = ProcessadorIncremental(); alertas = p.processar_paciente(\'PAC-0001\'); print(f\'Alertas: {len(alertas)}\')"')
