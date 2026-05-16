# Genera deploy/vps/.env desde deploy/render.env + tu dominio API
param(
    [string]$ApiDomain = ""
)

$ErrorActionPreference = "Stop"
$deploy = Split-Path $PSScriptRoot -Parent
$vps = $PSScriptRoot
$src = Join-Path $deploy "render.env"
$dst = Join-Path $vps ".env"

if (-not (Test-Path $src)) {
    Write-Error "Falta deploy/render.env"
}

if (-not $ApiDomain) {
    Write-Host "Dominio de la API en el VPS (ej. api.midominio.com):" -ForegroundColor Cyan
    $ApiDomain = (Read-Host).Trim()
}
if ($ApiDomain -notmatch '\.') {
    Write-Error "Dominio invalido: $ApiDomain"
}

$lines = @("API_DOMAIN=$ApiDomain")
Get-Content $src -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^\s*#' -or $line -eq '') { return }
    if ($line -match '^\s*API_DOMAIN\s*=') { return }
    if ($line -match '^\s*RENDER\s*=') { return }
    if ($line -match '^\s*PYTHON_VERSION\s*=') { return }

    if ($line -match '^\s*TWITCH_REDIRECT_URI\s*=') {
        $lines += "TWITCH_REDIRECT_URI=https://${ApiDomain}/api/v1/integrations/twitch/callback"
        return
    }
    if ($line -match '^\s*TWITCH_EVENTSUB_CALLBACK_URL\s*=') {
        $lines += "TWITCH_EVENTSUB_CALLBACK_URL=https://${ApiDomain}/api/v1/webhooks/twitch"
        return
    }
    if ($line -match '^\s*TRUSTED_HOSTS\s*=') {
        $base = ($ApiDomain -split '\.', 2)[1]
        if ($base) {
            $lines += "TRUSTED_HOSTS=${ApiDomain},.${base},localhost,127.0.0.1"
        } else {
            $lines += "TRUSTED_HOSTS=${ApiDomain},localhost,127.0.0.1"
        }
        return
    }

    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $key = $Matches[1]
        $val = $Matches[2].Trim()
        if ($val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $lines += "$key=$val"
    }
}

$lines | Set-Content $dst -Encoding UTF8
Write-Host "Creado $dst - $($lines.Count) variables" -ForegroundColor Green
Write-Host ""
Write-Host "Siguiente:" -ForegroundColor Cyan
Write-Host "  1. Sube el repo al VPS (git clone o scp)"
Write-Host ('  2. scp deploy/vps/.env user@IP:~/Anti-Bots/deploy/vps/.env')
Write-Host "  3. En el VPS: bash deploy/vps/setup-server.sh"
Write-Host ('  4. Vercel API_PROXY_TARGET=https://' + $ApiDomain)
