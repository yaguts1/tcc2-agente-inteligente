# Script para iniciar ambiente de desenvolvimento
# Executa Backend e Frontend em paralelo

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Iniciando Sistema de Agenda" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Obter diretório raiz
$rootDir = Get-Location

# Verificar se está no diretório correto
if (-not (Test-Path "interface\web.py")) {
    Write-Host "ERRO: Execute este script da raiz do projeto!" -ForegroundColor Red
    exit 1
}

Write-Host "Root Dir: $rootDir" -ForegroundColor Yellow
Write-Host ""

# Terminal 1: Backend
Write-Host "Iniciando Backend..." -ForegroundColor Green
$backend = Start-Process -NoNewWindow -RedirectStandardOutput "$rootDir\backend.log" `
    -FilePath "powershell.exe" `
    -ArgumentList @"
    cd '$rootDir'; 
    Write-Host 'Backend iniciando em 8000...' -ForegroundColor Cyan;
    uvicorn interface.web:app --reload --host 0.0.0.0 --port 8000
"@

Write-Host "Backend PID: $($backend.Id)" -ForegroundColor Yellow

# Aguardar 3 segundos
Start-Sleep -Seconds 3

# Terminal 2: Frontend
Write-Host "Iniciando Frontend..." -ForegroundColor Green
$frontend = Start-Process -NoNewWindow -RedirectStandardOutput "$rootDir\frontend.log" `
    -FilePath "powershell.exe" `
    -ArgumentList @"
    cd '$rootDir\frontend'; 
    Write-Host 'Frontend iniciando em 5173...' -ForegroundColor Cyan;
    npm run dev
"@

Write-Host "Frontend PID: $($frontend.Id)" -ForegroundColor Yellow
Write-Host ""

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Sistemas iniciados!" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backend:  http://localhost:8000" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs:" -ForegroundColor Yellow
Write-Host "Backend:  $rootDir\backend.log" -ForegroundColor Gray
Write-Host "Frontend: $rootDir\frontend.log" -ForegroundColor Gray
Write-Host ""
Write-Host "Para parar, execute:" -ForegroundColor Yellow
Write-Host "  Stop-Process -Id $($backend.Id), $($frontend.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "Aguardando 5 segundos antes de testar..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

# Testar conectividade
Write-Host ""
Write-Host "Testando conectividade..." -ForegroundColor Cyan

$maxRetries = 10
$retryCount = 0
$backendReady = $false
$frontendReady = $false

while ($retryCount -lt $maxRetries) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/api/pacientes/PAC-0001/agenda" -Method Get -TimeoutSec 1 -SkipHttpErrorCheck
        if ($resp.StatusCode -in @(200, 404)) { $backendReady = $true }
    } catch {}
    
    if ($backendReady) { break }
    $retryCount++
    Start-Sleep -Seconds 1
}

$retryCount = 0
while ($retryCount -lt $maxRetries) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:5173" -Method Get -TimeoutSec 1 -SkipHttpErrorCheck
        if ($resp.StatusCode -in @(200, 304)) { $frontendReady = $true }
    } catch {}
    
    if ($frontendReady) { break }
    $retryCount++
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "Status:" -ForegroundColor Yellow
Write-Host "Backend:  $(if ($backendReady) { 'READY' } else { 'WAITING' })" -ForegroundColor $(if ($backendReady) { 'Green' } else { 'Yellow' })
Write-Host "Frontend: $(if ($frontendReady) { 'READY' } else { 'WAITING' })" -ForegroundColor $(if ($frontendReady) { 'Green' } else { 'Yellow' })
Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "PRONTO PARA TESTAR!" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Abra o browser em: http://localhost:5173" -ForegroundColor Green
Write-Host ""
Write-Host "Para fechar tudo:" -ForegroundColor Yellow
Write-Host "  Get-Process | Where-Object { $_.ProcessName -match 'python|node' } | Stop-Process" -ForegroundColor Gray
