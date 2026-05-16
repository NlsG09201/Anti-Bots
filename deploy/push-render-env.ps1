# Wrapper: python deploy/push_render_env.py
param([string]$ServiceName = "anti-bots-api")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$deploy = $PSScriptRoot

& (Join-Path $deploy "prepare-render-import.ps1")

$keyFile = Join-Path $deploy "render.api.key"
if (-not $env:RENDER_API_KEY -and -not (Test-Path $keyFile)) {
    Write-Host ""
    Write-Host "Pega tu Render API Key completa (empieza con rnd_) y Enter:" -ForegroundColor Yellow
    Write-Host "Crear en: https://dashboard.render.com/u/settings#api-keys" -ForegroundColor Gray
    $key = (Read-Host).Trim()
    if ($key -notmatch '^rnd_') {
        Write-Host "ERROR: La clave debe empezar con rnd_. No uses un numero suelto." -ForegroundColor Red
        exit 1
    }
    [System.IO.File]::WriteAllText($keyFile, $key, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Guardada en deploy/render.api.key (sin BOM)" -ForegroundColor Green
} elseif (Test-Path $keyFile) {
    $existing = [System.IO.File]::ReadAllText($keyFile, [System.Text.UTF8Encoding]::new($false)).Trim().TrimStart([char]0xFEFF)
    if ($existing -notmatch '^rnd_') {
        Write-Host "ERROR: deploy/render.api.key invalida. Borrala y vuelve a ejecutar." -ForegroundColor Red
        Write-Host "  Remove-Item '$keyFile'" -ForegroundColor Gray
        exit 1
    }
}

if ($ServiceName) { $env:RENDER_SERVICE_NAME = $ServiceName }
python (Join-Path $deploy "push_render_env.py")
exit $LASTEXITCODE
