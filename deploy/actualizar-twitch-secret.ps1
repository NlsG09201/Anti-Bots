# Solo actualiza TWITCH_CLIENT_SECRET en Render (Client ID ya conocido)
param(
    [string]$ClientId = "afu46q601sn7xfukiskqrgvz2nkjqw",
    [Parameter(Mandatory = $false)]
    [string]$ClientSecret = ""
)

$ErrorActionPreference = "Stop"
$deploy = $PSScriptRoot
$keyFile = Join-Path $deploy "render.api.key"

if (-not $ClientSecret) {
    Write-Host ""
    Write-Host "Client ID (ya en Render): $ClientId" -ForegroundColor Gray
    Write-Host ""
    Write-Host "dev.twitch.tv -> tu app -> Client Secret -> New Secret" -ForegroundColor Cyan
    Write-Host "El Secret es OTRA cadena (no repitas el Client ID)." -ForegroundColor Yellow
    Write-Host ""
    $ClientSecret = (Read-Host "Pega Client Secret aqui").Trim()
}

if ($ClientId -eq $ClientSecret) {
    Write-Error "Pegaste el Client ID otra vez. En Twitch hay dos valores distintos: Client ID y Client Secret."
}
if ($ClientSecret.Length -lt 20) {
    Write-Error "Secret incompleto. Copialo entero desde Twitch."
}
if (-not (Test-Path $keyFile)) {
    Write-Error "Falta deploy/render.api.key"
}

& (Join-Path $deploy "prepare-render-import.ps1")
$tmp = Join-Path $deploy ".twitch-secret.tmp"
$ClientSecret | Set-Content $tmp -NoNewline -Encoding UTF8

$py = @"
import json, urllib.request
from pathlib import Path
key = Path(r'$keyFile').read_text(encoding='utf-8-sig').strip()
secret = Path(r'$tmp').read_text(encoding='utf-8-sig').strip()
sid = 'srv-d84gnav7f7vs73a392n0'
cid = '$ClientId'
vars = {
    'TWITCH_CLIENT_ID': cid,
    'TWITCH_CLIENT_SECRET': secret,
    'TWITCH_REDIRECT_URI': 'https://anti-bots.onrender.com/api/v1/integrations/twitch/callback',
}
for name, val in vars.items():
    req = urllib.request.Request(
        f'https://api.render.com/v1/services/{sid}/env-vars/{name}',
        data=json.dumps({'value': val}).encode(),
        method='PUT',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    )
    urllib.request.urlopen(req, timeout=60)
    print('OK', name)
print('ID==SEC:', cid == secret)
req = urllib.request.Request(
    f'https://api.render.com/v1/services/{sid}/deploys',
    data=json.dumps({'clearCache': 'do_not_clear'}).encode(),
    method='POST',
    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
)
urllib.request.urlopen(req, timeout=60)
print('Deploy OK')
"@
python -c $py
Remove-Item $tmp -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Espera 3 min -> https://anti-bots.vercel.app/dashboard/settings" -ForegroundColor Green
