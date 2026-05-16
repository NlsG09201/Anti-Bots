# Importar variables en Render SIN API key (pegar en dashboard)
$ErrorActionPreference = "Stop"
$deploy = $PSScriptRoot

& (Join-Path $deploy "prepare-render-import.ps1")
$importFile = Join-Path $deploy "render.import.env"
$content = Get-Content $importFile -Raw -Encoding UTF8
Set-Clipboard -Value $content

Write-Host ""
Write-Host "=== IMPORTAR EN RENDER (manual) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "28 variables copiadas al portapapeles." -ForegroundColor Green
Write-Host ""
Write-Host "1. Se abrira dashboard.render.com"
Write-Host "2. Clic en tu servicio: anti-bots-api"
Write-Host "3. Menu izquierdo: Environment"
Write-Host "4a. Add from .env -> Ctrl+V -> Save"
Write-Host "   O 4b. Secret Files -> subir este archivo como nombre: .env"
Write-Host "5. Manual Deploy"
Write-Host ""
Write-Host "DATABASE_URL incluida (Neon Anti-Bot)." -ForegroundColor Gray
Write-Host ""

Start-Process "https://dashboard.render.com"
Start-Sleep -Seconds 2
notepad $importFile
