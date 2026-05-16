# Sube variables a Render via API (sin pegar manualmente en el dashboard).
# Uso:
#   $env:RENDER_API_KEY = "rnd_..."   # https://dashboard.render.com/u/settings#api-keys
#   .\deploy\push-render-env.ps1
param(
    [string]$ServiceName = "anti-bots-api",
    [string]$ImportFile = ""
)

$ErrorActionPreference = "Stop"
$deployDir = $PSScriptRoot
if (-not $ImportFile) {
    & (Join-Path $deployDir "prepare-render-import.ps1")
    $ImportFile = Join-Path $deployDir "render.import.env"
}

$apiKey = $env:RENDER_API_KEY
if (-not $apiKey) {
    Write-Host "Falta RENDER_API_KEY." -ForegroundColor Red
    Write-Host "1. https://dashboard.render.com/u/settings#api-keys -> Create API Key"
    Write-Host "2. `$env:RENDER_API_KEY = 'rnd_...'"
    Write-Host "3. Vuelve a ejecutar: .\deploy\push-render-env.ps1"
    exit 1
}

$headers = @{
    Authorization = "Bearer $apiKey"
    Accept        = "application/json"
    "Content-Type" = "application/json"
}

Write-Host "Buscando servicio $ServiceName..." -ForegroundColor Cyan
$services = Invoke-RestMethod -Uri "https://api.render.com/v1/services?limit=100" -Headers $headers
$service = $services | ForEach-Object { $_.service } | Where-Object { $_.name -eq $ServiceName } | Select-Object -First 1
if (-not $service) {
    Write-Host "No se encontro el servicio '$ServiceName'. Servicios:" -ForegroundColor Yellow
    $services | ForEach-Object { $_.service.name } | Sort-Object
    exit 1
}
$serviceId = $service.id
Write-Host "Servicio: $($service.name) ($serviceId)"

$envVars = @()
Get-Content $ImportFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $key = $Matches[1]
        $val = $Matches[2].Trim()
        if ($val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $envVars += @{ key = $key; value = $val }
    }
}

Write-Host "Subiendo $($envVars.Count) variables..." -ForegroundColor Cyan
$body = $envVars | ConvertTo-Json -Depth 3 -Compress
Invoke-RestMethod -Method Put -Uri "https://api.render.com/v1/services/$serviceId/env-vars" -Headers $headers -Body $body | Out-Null

Write-Host "OK: Variables actualizadas. Desplegando..." -ForegroundColor Green
try {
    Invoke-RestMethod -Method Post -Uri "https://api.render.com/v1/services/$serviceId/deploys" -Headers $headers -Body '{}' | Out-Null
    Write-Host "Deploy iniciado. Revisa logs en Render." -ForegroundColor Green
} catch {
    Write-Host "Variables guardadas. Inicia Manual Deploy en el dashboard si no arranco solo." -ForegroundColor Yellow
}

if ($service.serviceDetails -and $service.serviceDetails.url) {
    Write-Host "URL: $($service.serviceDetails.url)/health"
} else {
    Write-Host "URL: https://$ServiceName.onrender.com/health"
}
