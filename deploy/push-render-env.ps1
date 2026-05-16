# Wrapper: python deploy/push_render_env.py
param([string]$ServiceName = "anti-bots-api")

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$deploy = $PSScriptRoot

& (Join-Path $deploy "prepare-render-import.ps1")

$keyFile = Join-Path $deploy "render.api.key"
if (-not $env:RENDER_API_KEY -and -not (Test-Path $keyFile)) {
    Write-Host ""
    Write-Host "A) API key rnd_... (automatico)  |  B) Manual sin API (pegar en web)" -ForegroundColor Cyan
    Write-Host "Escribe A o B y Enter:" -ForegroundColor Yellow
    $choice = (Read-Host).Trim().ToUpper()
    if ($choice -eq "B" -or $choice -eq "M") {
        & (Join-Path $deploy "import-render-manual.ps1")
        exit 0
    }
    Write-Host ""
    Write-Host "Pega la API key COMPLETA (rnd_...) y Enter:" -ForegroundColor Yellow
    Write-Host "https://dashboard.render.com/u/settings#api-keys" -ForegroundColor Gray
    $key = (Read-Host).Trim().TrimStart([char]0xFEFF)
    if ($key -notmatch '^rnd_') {
        Write-Host "ERROR: Debe empezar con rnd_. Ejecuta: .\import-render-manual.ps1" -ForegroundColor Red
        exit 1
    }
    [System.IO.File]::WriteAllText($keyFile, $key, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Guardada en deploy/render.api.key" -ForegroundColor Green
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
