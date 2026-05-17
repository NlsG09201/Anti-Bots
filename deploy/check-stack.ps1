# Comprueba Render + proxy Vercel
param([string]$RenderUrl = "https://anti-bots.onrender.com")

$ErrorActionPreference = "Continue"
Write-Host "=== Diagnostico StreamShield ===" -ForegroundColor Cyan

$renderHealth = "$RenderUrl/health"
try {
    $r = Invoke-WebRequest -Uri $renderHealth -UseBasicParsing -TimeoutSec 45
    Write-Host "[OK] Render $renderHealth -> $($r.StatusCode)" -ForegroundColor Green
    Write-Host "     $($r.Content.Substring(0, [Math]::Min(120, $r.Content.Length)))"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host "[FAIL] Render $renderHealth -> $code" -ForegroundColor Red
    Write-Host "     La API no esta viva. Render -> Environment -> import render.import.env -> Save -> Manual Deploy"
}

$vercelCsrf = "https://anti-bots.vercel.app/api/v1/auth/csrf"
try {
    $r = Invoke-WebRequest -Uri $vercelCsrf -UseBasicParsing -TimeoutSec 45
    Write-Host "[OK] Vercel proxy $vercelCsrf -> $($r.StatusCode)" -ForegroundColor Green
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host "[FAIL] Vercel proxy $vercelCsrf -> $code" -ForegroundColor Red
    if ($code -eq 404) {
        Write-Host "     404 aqui casi siempre = Render caido (Vercel reenvia a Render)."
    }
}

Write-Host ""
