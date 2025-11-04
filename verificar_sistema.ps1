# Script de Verificação de Saúde do Sistema
# Uso: .\verificar_sistema.ps1

Write-Host "`n=== VERIFICAÇÃO DE SAÚDE DO SISTEMA ===" -ForegroundColor Cyan
Write-Host "Checando componentes...`n" -ForegroundColor Yellow

$todosOk = $true

# 1. Backend (FastAPI)
Write-Host "[1/6] Backend API..." -ForegroundColor Green
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stats" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $stats = $response.Content | ConvertFrom-Json
    Write-Host "  ✓ API respondendo" -ForegroundColor Green
    Write-Host "    → Pacientes monitorados: $($stats.pacientes_monitorados)" -ForegroundColor Gray
    Write-Host "    → Alertas ativos: $($stats.alertas_ativos)" -ForegroundColor Gray
} catch {
    Write-Host "  ✗ API NÃO está respondendo!" -ForegroundColor Red
    Write-Host "    → Iniciar: .\venv\Scripts\python.exe -m uvicorn interface.web:app --reload" -ForegroundColor Yellow
    $todosOk = $false
}

# 2. Frontend (Vite)
Write-Host "`n[2/6] Frontend..." -ForegroundColor Green
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  ✓ Frontend acessível" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Frontend NÃO está acessível!" -ForegroundColor Red
    Write-Host "    → Iniciar: cd frontend; npm run dev" -ForegroundColor Yellow
    $todosOk = $false
}

# 3. Banco de Dados
Write-Host "`n[3/6] Banco de Dados..." -ForegroundColor Green
if (Test-Path "dados.db") {
    Write-Host "  ✓ Arquivo dados.db existe" -ForegroundColor Green
    
    $stats = .\venv\Scripts\python.exe -c @"
import sqlite3
conn = sqlite3.connect('dados.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM pacientes')
pacientes = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM alertas')
alertas = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM grade')
eventos = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM device_events WHERE processed = 0')
orfaos = cursor.fetchone()[0]

print(f'{pacientes}|{alertas}|{eventos}|{orfaos}')
conn.close()
"@
    
    $valores = $stats -split '\|'
    Write-Host "    → Pacientes: $($valores[0])" -ForegroundColor Gray
    Write-Host "    → Alertas: $($valores[1])" -ForegroundColor Gray
    Write-Host "    → Eventos de grade: $($valores[2])" -ForegroundColor Gray
    Write-Host "    → Eventos órfãos: $($valores[3])" -ForegroundColor Gray
} else {
    Write-Host "  ✗ Arquivo dados.db NÃO encontrado!" -ForegroundColor Red
    $todosOk = $false
}

# 4. Python Virtual Environment
Write-Host "`n[4/6] Ambiente Python..." -ForegroundColor Green
if (Test-Path "venv\Scripts\python.exe") {
    Write-Host "  ✓ Virtual environment existe" -ForegroundColor Green
    
    $pythonVersion = .\venv\Scripts\python.exe --version
    Write-Host "    → $pythonVersion" -ForegroundColor Gray
    
    # Verificar pacotes críticos
    $pacotes = .\venv\Scripts\python.exe -c @"
try:
    import fastapi
    import uvicorn
    import pandas
    import numpy
    import pydantic
    import structlog
    print('OK')
except ImportError as e:
    print(f'ERRO: {e}')
"@
    
    if ($pacotes -eq "OK") {
        Write-Host "    → Dependências instaladas" -ForegroundColor Gray
    } else {
        Write-Host "  ✗ Dependências faltando!" -ForegroundColor Red
        Write-Host "    → Instalar: .\venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
        $todosOk = $false
    }
} else {
    Write-Host "  ✗ Virtual environment NÃO encontrado!" -ForegroundColor Red
    Write-Host "    → Criar: python -m venv venv" -ForegroundColor Yellow
    $todosOk = $false
}

# 5. Node.js e npm
Write-Host "`n[5/6] Node.js..." -ForegroundColor Green
try {
    $nodeVersion = node --version
    $npmVersion = npm --version
    Write-Host "  ✓ Node.js instalado" -ForegroundColor Green
    Write-Host "    → Node: $nodeVersion" -ForegroundColor Gray
    Write-Host "    → npm: $npmVersion" -ForegroundColor Gray
    
    if (Test-Path "frontend\node_modules") {
        Write-Host "    → Dependências instaladas" -ForegroundColor Gray
    } else {
        Write-Host "  ⚠ Dependências do frontend não instaladas" -ForegroundColor Yellow
        Write-Host "    → Instalar: cd frontend; npm install" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ Node.js NÃO encontrado!" -ForegroundColor Red
    $todosOk = $false
}

# 6. WebSocket
Write-Host "`n[6/6] WebSocket..." -ForegroundColor Green
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stats" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  ✓ Endpoint WebSocket disponível (ws://127.0.0.1:8000/api/ws/alerts)" -ForegroundColor Green
    Write-Host "    → Verificar conexão no browser DevTools (Network → WS)" -ForegroundColor Gray
} catch {
    Write-Host "  ✗ Não foi possível verificar WebSocket" -ForegroundColor Red
}

# Resumo Final
Write-Host "`n" + ("=" * 50) -ForegroundColor Cyan
if ($todosOk) {
    Write-Host "✅ SISTEMA SAUDÁVEL - Pronto para uso!" -ForegroundColor Green
    Write-Host "`nAcesse:" -ForegroundColor Cyan
    Write-Host "  • Frontend: http://localhost:5173" -ForegroundColor White
    Write-Host "  • API Docs: http://127.0.0.1:8000/docs" -ForegroundColor White
} else {
    Write-Host "⚠️ PROBLEMAS DETECTADOS - Verificar logs acima" -ForegroundColor Yellow
}
Write-Host ("=" * 50) + "`n" -ForegroundColor Cyan
