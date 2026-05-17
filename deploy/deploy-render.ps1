# Render + Vercel: preparar env, abrir dashboard, configurar Vercel
param(
    [string]$RenderServiceUrl = "https://anti-bots-api.onrender.com",
    [switch]$SkipVercel,
    [switch]$SkipRenderOpen
)

$ErrorActionPreference = "Stop"
$deploy = $PSScriptRoot

Write-Host ""
Write-Host "=== StreamShield: Render + Vercel ===" -ForegroundColor Cyan
Write-Host ""

& (Join-Path $deploy "prepare-render-import.ps1")

$importFile = Join-Path $deploy "render.import.env"
$count = (Get-Content $importFile | Where-Object { $_ -match '=' }).Count
Set-Clipboard -Value (Get-Content $importFile -Raw -Encoding UTF8)

Write-Host "OK $count variables en portapapeles ($importFile)" -ForegroundColor Green
Write-Host ""

if (-not $SkipRenderOpen) {
    Write-Host "--- RENDER (haz esto ahora) ---" -ForegroundColor Yellow
    Write-Host "  1. Servicio anti-bots-api -> Environment -> Add from .env"
    Write-Host "  2. Ctrl+V -> Save Changes"
    Write-Host "  3. Start Command: vacio O preflight+uvicorn (ver RENDER_VERCEL.md)"
    Write-Host "  4. Manual Deploy"
    Write-Host ""
    Start-Process "https://dashboard.render.com"
    Start-Sleep -Seconds 1
    notepad $importFile
}

Write-Host "Cuando /health responda, pulsa Enter para copiar vars de Vercel..." -ForegroundColor Gray
if (-not $SkipVercel) {
    Read-Host | Out-Null
    & (Join-Path $deploy "vercel-conectar.ps1") -ApiUrl $RenderServiceUrl
}

Write-Host ""
Write-Host "Guia completa: deploy\RENDER_VERCEL.md" -ForegroundColor Cyan
