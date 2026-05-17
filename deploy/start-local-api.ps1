# Levanta API local con Docker (mismas vars que Render) — prueba sin Render
$ErrorActionPreference = "Stop"
$deploy = $PSScriptRoot

& (Join-Path $deploy "prepare-render-import.ps1")

Write-Host "Build y arranque en http://localhost:8000 ..." -ForegroundColor Cyan
Push-Location (Join-Path $deploy "local")
try {
    docker compose up --build -d
    Write-Host "Esperando health..." -ForegroundColor Gray
    for ($i = 1; $i -le 24; $i++) {
        Start-Sleep -Seconds 5
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 5
            Write-Host "OK: $($r.Content)" -ForegroundColor Green
            Write-Host "Docs: http://127.0.0.1:8000/docs (si APP_DEBUG=true)" -ForegroundColor Gray
            exit 0
        } catch {
            Write-Host "  $i/24..." -ForegroundColor DarkGray
        }
    }
    docker compose logs api --tail 40
    Write-Error "API no respondio en 2 min"
} finally {
    Pop-Location
}
