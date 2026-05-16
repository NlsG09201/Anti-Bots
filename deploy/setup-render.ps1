# Prepara variables para Render y las copia al portapapeles
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "=== StreamShield - Setup Render ===" -ForegroundColor Cyan

& (Join-Path $PSScriptRoot "prepare-render-import.ps1")

$importFile = Join-Path $PSScriptRoot "render.import.env"
$content = Get-Content $importFile -Raw -Encoding UTF8
Set-Clipboard -Value $content

Write-Host ""
Write-Host "OK: Variables copiadas al portapapeles." -ForegroundColor Green
Write-Host ""
if ($env:RENDER_API_KEY -or (Test-Path (Join-Path $PSScriptRoot "render.api.key"))) {
    & (Join-Path $PSScriptRoot "push-render-env.ps1")
    exit $LASTEXITCODE
}

Write-Host "Opcion A (API):"
Write-Host '  $env:RENDER_API_KEY = "rnd_..."'
Write-Host "  .\deploy\push-render-env.ps1"
Write-Host ""
Write-Host "Opcion B (manual):"
Write-Host "1. Abre https://dashboard.render.com"
Write-Host "2. Servicio anti-bots-api -> Environment"
Write-Host "3. Add from .env -> Ctrl+V -> Save Changes"
Write-Host "4. Manual Deploy"
Write-Host ""
Write-Host "Probar Neon localmente:"
Write-Host "  cd backend"
Write-Host "  python -m scripts.test_neon_connection"

Start-Process "https://dashboard.render.com"
