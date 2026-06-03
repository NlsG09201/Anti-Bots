# Un solo script: verifica Neon, prepara Render, copia al portapapeles, abre dashboards
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$deploy = $PSScriptRoot
$backend = Join-Path $root "backend"

Write-Host ""
Write-Host "========== StreamShield DEPLOY ==========" -ForegroundColor Cyan
Write-Host ""

# 1 Neon
Write-Host "[1/4] Probando Neon..." -ForegroundColor Yellow
Push-Location $backend
python -m scripts.test_neon_connection
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Host "FALLO Neon. Revisa DATABASE_URL en deploy/render.env" -ForegroundColor Red
    exit 1
}
Pop-Location
Write-Host "OK Neon" -ForegroundColor Green

# 2 Render import file
Write-Host "[2/4] Generando render.import.env..." -ForegroundColor Yellow
& (Join-Path $deploy "prepare-render-import.ps1") | Out-Null
$importFile = Join-Path $deploy "render.import.env"
$content = Get-Content $importFile -Raw -Encoding UTF8
Set-Clipboard -Value $content
Write-Host "OK 28 variables en portapapeles" -ForegroundColor Green

# 3 Instrucciones Render
Write-Host ""
Write-Host "[3/4] RENDER (hazlo ahora en el navegador):" -ForegroundColor Yellow
Write-Host "  Servicio: anti-bots-api"
Write-Host "  Opcion A: Environment -> Add from .env -> Ctrl+V -> Save"
Write-Host "  Opcion B: Environment -> Secret Files -> subir render.import.env como .env"
Write-Host "  Luego: Manual Deploy"
Write-Host "  Health: https://anti-bots.onrender.com/health"
Write-Host ""

Start-Process "https://dashboard.render.com"
Start-Sleep -Seconds 1
notepad $importFile

# 4 Vercel
Write-Host "[4/4] VERCEL (dashboard.vercel.com -> proyecto -> Settings -> Environment):" -ForegroundColor Yellow
Write-Host "  API_PROXY_TARGET=https://anti-bots.onrender.com"
Write-Host "  NEXT_PUBLIC_WS_URL=wss://anti-bots.onrender.com"
Write-Host "  (NO pongas NEXT_PUBLIC_API_URL=localhost)"
Write-Host ""
Write-Host "Cuando Render este Live, redeploy Vercel." -ForegroundColor Gray
Write-Host ""
Write-Host "========== Listo (pega en Render con Ctrl+V) ==========" -ForegroundColor Green
