# Script de Reset e Preparação para Demonstração
# Uso: .\preparar_demo.ps1

Write-Host "`n=== PREPARAÇÃO PARA DEMONSTRAÇÃO ===" -ForegroundColor Cyan
Write-Host "Este script irá preparar o ambiente com dados frescos`n" -ForegroundColor Yellow

# 1. Verificar se servidor está rodando
Write-Host "[1/5] Verificando serviços..." -ForegroundColor Green
try {
    $backend = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stats" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  ✓ Backend está rodando" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Backend NÃO está rodando!" -ForegroundColor Red
    Write-Host "  → Execute: .\venv\Scripts\python.exe -m uvicorn interface.web:app --reload" -ForegroundColor Yellow
    exit 1
}

# 2. Limpar dados antigos de demonstração
Write-Host "`n[2/5] Limpando dados antigos..." -ForegroundColor Green
.\venv\Scripts\python.exe -c @"
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

# Remover pacientes de demo anteriores
cursor.execute('DELETE FROM alertas WHERE paciente_id LIKE \"DEMO-%\"')
cursor.execute('DELETE FROM grade WHERE paciente_id LIKE \"DEMO-%\"')
cursor.execute('DELETE FROM pacientes WHERE id LIKE \"DEMO-%\"')

# Limpar eventos órfãos antigos (> 7 dias)
limite = (datetime.now() - timedelta(days=7)).isoformat()
cursor.execute('DELETE FROM device_events WHERE ts_iso < ?', (limite,))

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
"@

# 3. Gerar pacientes de demonstração
Write-Host "`n[3/5] Gerando pacientes de demonstração..." -ForegroundColor Green

Write-Host "  → DEMO-ALTO: Paciente alto risco (24h de dados)..." -ForegroundColor Yellow
.\venv\Scripts\python.exe testar_simulacao_com_verificacao.py DEMO-ALTO 24 alto | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ Gerado com sucesso" -ForegroundColor Green
} else {
    Write-Host "    ✗ Falha na geração" -ForegroundColor Red
}

Write-Host "  → DEMO-MEDIO: Paciente risco médio (24h de dados)..." -ForegroundColor Yellow
.\venv\Scripts\python.exe testar_simulacao_com_verificacao.py DEMO-MEDIO 24 medio | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ Gerado com sucesso" -ForegroundColor Green
} else {
    Write-Host "    ✗ Falha na geração" -ForegroundColor Red
}

Write-Host "  → DEMO-BAIXO: Paciente baixo risco (24h de dados)..." -ForegroundColor Yellow
.\venv\Scripts\python.exe testar_simulacao_com_verificacao.py DEMO-BAIXO 24 baixo | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ Gerado com sucesso" -ForegroundColor Green
} else {
    Write-Host "    ✗ Falha na geração" -ForegroundColor Red
}

# 4. Criar alguns eventos órfãos para demonstração de reconciliação
Write-Host "`n[4/5] Criando eventos órfãos para demo de reconciliação..." -ForegroundColor Green
.\venv\Scripts\python.exe -c @"
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
            INSERT INTO device_events (device_id, ts_iso, ts_ms, payload, processed)
            VALUES (?, ?, ?, ?, 0)
        ''', (f'ESP32-{leito}', ts_iso, ts_ms, json.dumps(payload)))

conn.commit()

# Verificar
cursor.execute('SELECT COUNT(*) FROM device_events WHERE processed = 0')
orfaos = cursor.fetchone()[0]
print(f'  ✓ {orfaos} eventos órfãos criados para demonstração')

conn.close()
"@

# 5. Verificação final
Write-Host "`n[5/5] Verificação final..." -ForegroundColor Green
.\venv\Scripts\python.exe -c @"
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
cursor.execute('SELECT COUNT(*) FROM alertas WHERE paciente_id LIKE \"DEMO-%\" AND inicio >= ?', (limite_24h,))
alertas_24h = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM device_events WHERE processed = 0')
orfaos = cursor.fetchone()[0]

print(f'`n  📊 RESUMO DO AMBIENTE:')
print(f'  ─────────────────────────────────')
print(f'  Pacientes de demo: {len(pacientes_demo)}')
for pac_id, cama_id in pacientes_demo:
    leito = cama_id if cama_id else '(sem leito)'
    print(f'    • {pac_id} - Leito: {leito}')

print(f'`n  Alertas (últimas 24h): {alertas_24h}')
print(f'  Eventos órfãos: {orfaos}')
print(f'  ─────────────────────────────────')

conn.close()
"@

# Sucesso!
Write-Host "`n✅ AMBIENTE PRONTO PARA DEMONSTRAÇÃO!`n" -ForegroundColor Green
Write-Host "Próximos passos:" -ForegroundColor Cyan
Write-Host "  1. Abrir frontend: http://localhost:5173" -ForegroundColor White
Write-Host "  2. Ir para Dashboard e filtrar por 'DEMO-'" -ForegroundColor White
Write-Host "  3. Ver eventos órfãos em Admin → Device Events" -ForegroundColor White
Write-Host "  4. Explorar Timeline dos pacientes DEMO-ALTO, DEMO-MEDIO, DEMO-BAIXO`n" -ForegroundColor White
