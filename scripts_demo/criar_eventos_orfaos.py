"""Cria eventos órfãos para demonstração de reconciliação."""
import sqlite3
import json
from datetime import datetime, timedelta

conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Criar eventos órfãos em leitos fictícios
leitos = ['C-99', 'C-98', 'C-97']
agora = datetime.now()

for i, leito in enumerate(leitos):
    # 3-5 eventos por leito
    num_eventos = 3 + i
    for j in range(num_eventos):
        ts = agora - timedelta(hours=i+1, minutes=j*10)
        ts_iso = ts.strftime('%Y-%m-%dT%H:%M:%S')
        ts_ms = int(ts.timestamp() * 1000)
        
        payload = {
            'device_id': f'ESP32-{leito}',
            'cama_id': leito,
            'postura': 'supino' if j % 2 == 0 else 'lateral_direito',
            'confianca': 0.95,
            'amostra_ms': 100,
            'ts_utc': ts_iso
        }
        
        cursor.execute('''
            INSERT INTO device_events (device_id, ts, ts_ms, payload)
            VALUES (?, ?, ?, ?)
        ''', (f'ESP32-{leito}', ts_iso, ts_ms, json.dumps(payload)))

conn.commit()

# Verificar
cursor.execute('SELECT COUNT(*) FROM device_events WHERE processed_at IS NULL')
orfaos = cursor.fetchone()[0]
print(f'  ✓ {orfaos} eventos órfãos criados para demonstração')

conn.close()
