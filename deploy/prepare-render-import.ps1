# Genera deploy/render.import.env (sin comentarios ni comillas innecesarias)
$src = Join-Path $PSScriptRoot "render.env"
$dst = Join-Path $PSScriptRoot "render.import.env"

if (-not (Test-Path $src)) {
    Write-Error "Missing deploy/render.env"
    exit 1
}

$lines = @()
$values = @{}
Get-Content $src -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^\s*#' -or $line -eq '') { return }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $key = $Matches[1]
        $val = $Matches[2].Trim()
        if ($val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $values[$key] = $val
        $lines += "$key=$val"
    }
}

# These values are required by the production startup checks. Do not create a
# partial import that would replace valid Render settings with missing values.
$problems = @()
$trustedHosts = @($values['TRUSTED_HOSTS'] -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() })
if (-not $trustedHosts -or $trustedHosts -contains '') {
    $problems += 'TRUSTED_HOSTS is empty; use the public Render hostnames.'
} elseif ($trustedHosts | Where-Object { $_ -in @('localhost', '127.0.0.1', '::1', '*') }) {
    $problems += 'TRUSTED_HOSTS contains a loopback host or wildcard; use anti-bots.onrender.com,anti-bots-api.onrender.com.'
}
if ([string]::IsNullOrWhiteSpace($values['REDIS_URL'])) {
    $problems += 'REDIS_URL is blank; set the native redis:// or rediss:// connection URL (Upstash REST credentials are not a substitute).'
} elseif ($values['REDIS_URL'] -notmatch '^rediss?://[^\s/]+') {
    $problems += 'REDIS_URL must be a native Redis TCP URL starting with redis:// or rediss://; Upstash REST HTTPS URLs are cache-only.'
}
if ($problems.Count -gt 0) {
    $problems | ForEach-Object { Write-Error $_ }
    Write-Error 'No import file was generated. Update deploy/render.env, then run this script again.'
    exit 1
}

$lines | Set-Content $dst -Encoding UTF8
Write-Host "Created $dst ($($lines.Count) variables, sin comillas)"
