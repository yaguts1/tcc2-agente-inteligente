import requests
import time
from datetime import datetime, timedelta

# Configuração
BASE_URL = "http://localhost:8000"
DEVICE_ID = "DEV-TEST-001"
PACIENTE_ID = "PAC-0001"
NUM_EVENTOS = 5
POSTURA = "decubito_dorsal"

print("=== TESTE VIA REST API ===")
print(f"Enviando {NUM_EVENTOS} eventos via POST /api/frontend/eventos")
print()

inicio = datetime.now()

for i in range(NUM_EVENTOS):
    timestamp = inicio + timedelta(seconds=i * 30)
    
    evento = {
        "device_id": DEVICE_ID,
        "paciente_id": PACIENTE_ID,
        "tipo": POSTURA,
        "inicio": timestamp.isoformat(),
        "fim": timestamp.isoformat(),
        "confianca": 0.95
    }
    
    print(f"[{i+1}/{NUM_EVENTOS}] Enviando evento (postura: {POSTURA})...")
    
    response = requests.post(
        f"{BASE_URL}/api/frontend/eventos",
        json=[evento]  # API aceita array
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"     Aceito! Processados: {data.get('events_processed', 0)}, Alertas: {data.get('alertas_gerados', 0)}")
    else:
        print(f"     Erro {response.status_code}: {response.text}")
    
    if i < NUM_EVENTOS - 1:
        time.sleep(30)  # Aguardar 30s entre eventos

print()
print("=== Verificando alertas gerados ===")
response = requests.get(f"{BASE_URL}/api/frontend/alerts")
if response.status_code == 200:
    alertas = response.json()
    print(f"Total de alertas: {len(alertas)}")
    for alerta in alertas[-3:]:  # Últimos 3
        print(f"  - {alerta.get('paciente_id')}: {alerta.get('tipo')} ({alerta.get('perfil')})")
else:
    print(f"Erro ao buscar alertas: {response.status_code}")

print()
print(" TESTE CONCLUÍDO!")
