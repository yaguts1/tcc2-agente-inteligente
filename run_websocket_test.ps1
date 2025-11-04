# Script PowerShell para testar o fluxo WebSocket
# Inicia o servidor, executa o teste e encerra

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "TESTE DE FLUXO WEBSOCKET - AUTOMÁTICO" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Caminho do Python
$pythonPath = "C:/Users/thiag.AIGOOO/Documents/TCC/tcc2-agente-inteligente/venv/Scripts/python.exe"

# 1. Iniciar servidor em background
Write-Host "[1/4] Iniciando servidor FastAPI..." -ForegroundColor Yellow
$serverProcess = Start-Process -FilePath $pythonPath `
    -ArgumentList "-m", "uvicorn", "interface.web:app", "--port", "8000" `
    -PassThru `
    -WindowStyle Hidden

Write-Host "      Servidor iniciado (PID: $($serverProcess.Id))" -ForegroundColor Green

# 2. Aguardar servidor ficar pronto
Write-Host "[2/4] Aguardando servidor ficar pronto (10 segundos)..." -ForegroundColor Yellow
Start-Sleep -Seconds 10
Write-Host "      Servidor pronto!" -ForegroundColor Green

# 3. Executar teste
Write-Host "[3/4] Executando teste WebSocket..." -ForegroundColor Yellow
Write-Host ""
& $pythonPath test_websocket_flow.py
Write-Host ""

# 4. Encerrar servidor
Write-Host "[4/4] Encerrando servidor..." -ForegroundColor Yellow
Stop-Process -Id $serverProcess.Id -Force
Write-Host "      Servidor encerrado" -ForegroundColor Green

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "TESTE CONCLUÍDO" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
