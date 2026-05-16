# Genera deploy/render.import.env para pegar en Render -> Add from .env
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
        if ($key -eq 'DATABASE_URL') {
            $lines += "$key=$val"
        } elseif ($val -match '^".*"$') {
            $lines += "$key=$val"
        } elseif ($val -match '[\s+#=]' -or $val -match '\+') {
            $escaped = $val -replace '"', '\"'
            $lines += "$key=`"$escaped`""
        } else {
            $lines += "$key=$val"
        }
    }
}
$lines | Set-Content $dst -Encoding UTF8
Write-Host "Created $dst ($($lines.Count) variables)"
