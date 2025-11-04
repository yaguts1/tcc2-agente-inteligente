# Script para iniciar todos os serviços
# Uso: .\iniciar_tudo.ps1

Write-Host "`n=== INICIANDO SISTEMA COMPLETO ===" -ForegroundColor Cyan

# 1. Verificar se já há processos rodando
Write-Host "`n[1/3] Verificando processos existentes..." -ForegroundColor Green

$backendRodando = $null
try {
    $backendRodando = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stats" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  ⚠ Backend já está rodando na porta 8000" -ForegroundColor Yellow
} catch {
    Write-Host "  ✓ Porta 8000 disponível" -ForegroundColor Green
}

$frontendRodando = $null
try {
    $frontendRodando = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  ⚠ Frontend já está rodando na porta 5173" -ForegroundColor Yellow
} catch {
    Write-Host "  ✓ Porta 5173 disponível" -ForegroundColor Green
}

# 2. Iniciar Backend (se não estiver rodando)
if (-not $backendRodando) {
    Write-Host "`n[2/3] Iniciando Backend..." -ForegroundColor Green
    
    # Criar novo terminal para backend
    Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
Write-Host '=== BACKEND (uvicorn) ===' -ForegroundColor Cyan;
cd '$PWD';
.\venv\Scripts\python.exe -m uvicorn interface.web:app --reload
"@
    
    # Aguardar inicialização
    Write-Host "  → Aguardando inicialização..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    
    # Verificar
    $tentativas = 0
    $maxTentativas = 10
    while ($tentativas -lt $maxTentativas) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stats" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            Write-Host "  ✓ Backend iniciado com sucesso!" -ForegroundColor Green
            break
        } catch {
            $tentativas++
            Start-Sleep -Seconds 1
        }
    }
    
    if ($tentativas -ge $maxTentativas) {
        Write-Host "  ✗ Backend não iniciou em tempo hábil" -ForegroundColor Red
        Write-Host "  → Verificar terminal do backend para erros" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n[2/3] Backend já está rodando - pulando..." -ForegroundColor Yellow
}

# 3. Iniciar Frontend (se não estiver rodando)
if (-not $frontendRodando) {
    Write-Host "`n[3/3] Iniciando Frontend..." -ForegroundColor Green
    
    # Verificar se node_modules existe
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "  ⚠ Dependências não instaladas - executando npm install..." -ForegroundColor Yellow
        cd frontend
        npm install
        cd ..
    }
    
    # Criar novo terminal para frontend
    Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
Write-Host '=== FRONTEND (Vite) ===' -ForegroundColor Cyan;
cd '$PWD\frontend';
npm run dev
"@
    
    # Aguardar inicialização
    Write-Host "  → Aguardando inicialização..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    
    # Verificar
    $tentativas = 0
    $maxTentativas = 10
    while ($tentativas -lt $maxTentativas) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            Write-Host "  ✓ Frontend iniciado com sucesso!" -ForegroundColor Green
            break
        } catch {
            $tentativas++
            Start-Sleep -Seconds 1
        }
    }
    
    if ($tentativas -ge $maxTentativas) {
        Write-Host "  ✗ Frontend não iniciou em tempo hábil" -ForegroundColor Red
        Write-Host "  → Verificar terminal do frontend para erros" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n[3/3] Frontend já está rodando - pulando..." -ForegroundColor Yellow
}

# Resumo
Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
Write-Host "✅ SISTEMA INICIADO!" -ForegroundColor Green
Write-Host "`nAcesse os serviços:" -ForegroundColor Cyan
Write-Host "  🌐 Frontend:  http://localhost:5173" -ForegroundColor White
Write-Host "  🔌 Backend:   http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  📚 API Docs:  http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "`nPara preparar dados de demonstração, execute:" -ForegroundColor Cyan
Write-Host "  .\preparar_demo.ps1" -ForegroundColor White
Write-Host ("=" * 60) + "`n" -ForegroundColor Cyan

# Abrir browser automaticamente (opcional)
Write-Host "Deseja abrir o navegador automaticamente? (S/N): " -NoNewline -ForegroundColor Yellow
$resposta = Read-Host

if ($resposta -eq "S" -or $resposta -eq "s") {
    Start-Process "http://localhost:5173"
    Write-Host "✓ Navegador aberto!" -ForegroundColor Green
}
