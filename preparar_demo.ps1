# Preparacao para Demonstracao

Write-Host ""
Write-Host "=== PREPARACAO PARA DEMONSTRACAO ===" -ForegroundColor Cyan
Write-Host ""

# Verificar backend
Write-Host "[1/3] Verificando backend..." -ForegroundColor Green
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/stats" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    Write-Host "  OK Backend rodando" -ForegroundColor Green
} catch {
    Write-Host "  ERRO Backend nao esta rodando!" -ForegroundColor Red
    Write-Host "  Execute: .\venv\Scripts\python.exe -m uvicorn interface.web:app --reload" -ForegroundColor Yellow
    exit 1
}

# Verificar pacientes
Write-Host ""
Write-Host "[2/3] Verificando pacientes..." -ForegroundColor Green
.\venv\Scripts\python.exe scripts_demo\verificar_pacientes.py
if ($LASTEXITCODE -ne 0) { exit 1 }

# Perguntar horas
Write-Host ""
Write-Host "Quantas horas de dados deseja gerar? (padrao: 24)" -ForegroundColor Cyan
$horas = Read-Host "Horas"
if ([string]::IsNullOrWhiteSpace($horas)) { $horas = 24 }

# Gerar dados
Write-Host ""
Write-Host "[3/3] Gerando dados ($horas horas)..." -ForegroundColor Green

$pacientes = .\venv\Scripts\python.exe scripts_demo\verificar_pacientes.py listar
foreach ($linha in $pacientes) {
    if ($linha -match '\|') {
        $partes = $linha -split '\|'
        $id = $partes[0].Trim()
        $perfil = $partes[1].Trim()
        
        Write-Host "  $id (perfil: $perfil)..." -ForegroundColor Yellow
        .\venv\Scripts\python.exe testar_simulacao_com_verificacao.py $id $horas $perfil 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    OK" -ForegroundColor Green
        }
    }
}

Write-Host ""
Write-Host "PRONTO!" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host "  Ver dados: .\venv\Scripts\python.exe ver_pacientes.py" -ForegroundColor Cyan
Write-Host ""
