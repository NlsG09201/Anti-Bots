# Genera deploy/render.import.env (sin comentarios ni comillas innecesarias)
$src = Join-Path $PSScriptRoot "render.env"
$dst = Join-Path $PSScriptRoot "render.import.env"

if (-not (Test-Path $src)) {
    Write-Error "Missing deploy/render.env"
    exit 1
}

$lines = @()
Get-Content $src -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^\s*#' -or $line -eq '') { return }
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
Write-Host "Created $dst ($($lines.Count) variables, sin comillas)"
