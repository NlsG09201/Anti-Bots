# Despliegue automatico Render + instrucciones Vercel
# Uso: .\do-it-all.ps1 -RenderApiKey "rnd_xxxxxxxx"
param(
    [Parameter(Mandatory = $false)]
    [string]$RenderApiKey = "",
    [string]$RenderServiceUrl = "https://anti-bots.onrender.com"
)

$ErrorActionPreference = "Stop"
$deploy = $PSScriptRoot

if (-not $RenderApiKey) {
    $keyFile = Join-Path $deploy "render.api.key"
    if (Test-Path $keyFile) {
        $RenderApiKey = [System.IO.File]::ReadAllText($keyFile, [System.Text.UTF8Encoding]::new($false)).Trim().TrimStart([char]0xFEFF)
    }
}
if (-not $RenderApiKey) {
    $RenderApiKey = $env:RENDER_API_KEY
}

if (-not $RenderApiKey -or $RenderApiKey -notmatch '^rnd_') {
    Write-Host ""
    Write-Host "Necesito tu Render API Key (una sola vez) para subir las variables." -ForegroundColor Yellow
    Write-Host "Crear en: https://dashboard.render.com/u/settings#api-keys" -ForegroundColor Gray
    Write-Host ""
    $RenderApiKey = (Read-Host "Pega rnd_...").Trim().TrimStart([char]0xFEFF)
    if ($RenderApiKey -notmatch '^rnd_') {
        Write-Error "Clave invalida. Debe empezar con rnd_"
    }
    [System.IO.File]::WriteAllText((Join-Path $deploy "render.api.key"), $RenderApiKey, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Guardada en deploy/render.api.key (gitignored)" -ForegroundColor Green
}

$env:RENDER_API_KEY = $RenderApiKey

& (Join-Path $deploy "prepare-render-import.ps1")
Write-Host ""
Write-Host "Subiendo variables a Render y lanzando deploy..." -ForegroundColor Cyan
python (Join-Path $deploy "push_render_env.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
& (Join-Path $deploy "vercel-conectar.ps1") -ApiUrl $RenderServiceUrl
Write-Host ""
Write-Host "Pega las variables en vercel.com y haz Redeploy del frontend." -ForegroundColor Yellow
