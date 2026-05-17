# Genera variables de Vercel para conectar el frontend con tu API
param(
    [Parameter(Mandatory = $false)]
    [string]$ApiUrl = ""
)

$ErrorActionPreference = "Stop"

if (-not $ApiUrl) {
    Write-Host "URL publica de tu API (sin barra final):" -ForegroundColor Cyan
    Write-Host "  Ej. https://api.midominio.com" -ForegroundColor Gray
    Write-Host "  Ej. https://anti-bots-api.onrender.com" -ForegroundColor Gray
    $ApiUrl = (Read-Host).Trim().TrimEnd("/")
}

if ($ApiUrl -notmatch '^https://') {
    Write-Error "La URL debe empezar con https://"
}

$wsUrl = $ApiUrl -replace '^https://', 'wss://'

$lines = @(
    "API_PROXY_TARGET=$ApiUrl"
    "NEXT_PUBLIC_WS_URL=$wsUrl"
    ""
    "# NO uses en Production:"
    "# NEXT_PUBLIC_API_URL=http://localhost:8000"
)

$block = $lines -join "`n"
Set-Clipboard -Value $block.Trim()

Write-Host ""
Write-Host "=== Variables para Vercel (Production) ===" -ForegroundColor Green
Write-Host $block
Write-Host ""
Write-Host "Copiado al portapapeles." -ForegroundColor Green
Write-Host ""
Write-Host "Pasos:" -ForegroundColor Cyan
Write-Host "  1. vercel.com -> tu proyecto -> Settings -> Environment Variables"
Write-Host "  2. Pega las 2 variables (Production)"
Write-Host "  3. Elimina NEXT_PUBLIC_API_URL si apunta a localhost"
Write-Host "  4. Deployments -> Redeploy"
Write-Host ""
Write-Host "Prueba API: curl $ApiUrl/health" -ForegroundColor Gray

# Comprobar health si hay red
try {
    $r = Invoke-WebRequest -Uri "$ApiUrl/health" -UseBasicParsing -TimeoutSec 15
    Write-Host "Health: OK $($r.StatusCode) $($r.Content.Substring(0, [Math]::Min(80, $r.Content.Length)))" -ForegroundColor Green
} catch {
    Write-Host "Health: aun no responde en $ApiUrl/health" -ForegroundColor Yellow
    Write-Host "  Despliega la API antes del redeploy de Vercel." -ForegroundColor Yellow
}
