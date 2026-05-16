# Wrapper: python deploy/push_render_env.py
param([string]$ServiceName = "anti-bots-api")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$deploy = $PSScriptRoot

& (Join-Path $deploy "prepare-render-import.ps1")

if (-not $env:RENDER_API_KEY -and -not (Test-Path (Join-Path $deploy "render.api.key"))) {
    Write-Host ""
    Write-Host "Pega tu Render API Key (rnd_...) y Enter:" -ForegroundColor Yellow
    Write-Host "Crear en: https://dashboard.render.com/u/settings#api-keys" -ForegroundColor Gray
    $key = Read-Host
    if ($key) {
        $key.Trim() | Set-Content (Join-Path $deploy "render.api.key") -Encoding UTF8 -NoNewline
        Write-Host "Guardada en deploy/render.api.key (gitignored)" -ForegroundColor Green
    }
}

if ($ServiceName) { $env:RENDER_SERVICE_NAME = $ServiceName }
python (Join-Path $deploy "push_render_env.py")
exit $LASTEXITCODE
