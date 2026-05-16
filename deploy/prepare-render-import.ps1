# Genera deploy/render.import.env (sin comentarios) para Render Add from .env
$src = Join-Path $PSScriptRoot "render.env"
$dst = Join-Path $PSScriptRoot "render.import.env"

if (-not (Test-Path $src)) {
    Write-Error "Missing render.env - fill deploy/render.required.env.example first."
    exit 1
}

Get-Content $src -Encoding UTF8 |
    Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' } |
    Set-Content $dst -Encoding UTF8

$count = (Get-Content $dst).Count
Write-Host "Created: $dst ($count variables)"
Write-Host "Next: copy file contents to Render Environment -> Add from .env -> Save -> Manual Deploy"
