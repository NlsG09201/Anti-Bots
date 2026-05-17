# Configura credenciales REALES de Twitch en Render
param(
    [string]$ClientId = "StreamShield2026!",
    [string]$ClientSecret = "StreamShield2026!"
)

$ErrorActionPreference = "Stop"
$deploy = $PSScriptRoot
$renderEnv = Join-Path $deploy "render.env"
$keyFile = Join-Path $deploy "render.api.key"

if (-not (Test-Path $renderEnv)) {
    Write-Error "Falta deploy/render.env"
}

if (-not $ClientId) {
    Write-Host ""
    Write-Host "=== Twitch Developer Console ===" -ForegroundColor Cyan
    Write-Host "1. https://dev.twitch.tv/console/apps -> Register App"
    Write-Host "2. OAuth Redirect URL:"
    Write-Host "   https://anti-bots.onrender.com/api/v1/integrations/twitch/callback" -ForegroundColor Green
    Write-Host "3. Client ID y Client Secret deben ser DIFERENTES" -ForegroundColor Yellow
    Write-Host ""
    $ClientId = (Read-Host "Client ID").Trim()
    $ClientSecret = (Read-Host "Client Secret").Trim()
}

if ($ClientId -eq $ClientSecret) {
    Write-Error "Client ID y Secret no pueden ser iguales."
}

$lines = Get-Content $renderEnv -Encoding UTF8
$out = @()
$map = @{
    "TWITCH_CLIENT_ID" = $ClientId
    "TWITCH_CLIENT_SECRET" = $ClientSecret
    "TWITCH_REDIRECT_URI" = "https://anti-bots.onrender.com/api/v1/integrations/twitch/callback"
    "TWITCH_EVENTSUB_CALLBACK_URL" = "https://anti-bots.onrender.com/api/v1/webhooks/twitch"
}
foreach ($line in $lines) {
    $replaced = $false
    foreach ($key in $map.Keys) {
        if ($line -match "^\s*$key\s*=") {
            $out += "$key=$($map[$key])"
            $replaced = $true
            break
        }
    }
    if (-not $replaced) { $out += $line }
}
$out | Set-Content $renderEnv -Encoding UTF8
Write-Host "Actualizado render.env" -ForegroundColor Green

if (-not (Test-Path $keyFile)) {
    Write-Host "Guarda Render API key en deploy/render.api.key y ejecuta: .\prepare-render-import.ps1; python push_render_env.py"
    exit 0
}

& (Join-Path $deploy "prepare-render-import.ps1")
$env:RENDER_API_KEY = [IO.File]::ReadAllText($keyFile).Trim()
$env:RENDER_SERVICE_NAME = "Anti-Bots"
python (Join-Path $deploy "push_render_env.py")

Write-Host ""
Write-Host "Espera 3 min y conecta en https://anti-bots.vercel.app/dashboard/settings" -ForegroundColor Green
