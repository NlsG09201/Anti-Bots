# Despliegue completo desde Windows: .env -> VPS -> Docker + Caddy
param(
    [string]$VpsIp = "",
    [string]$SshUser = "root",
    [string]$ApiDomain = "",
    [string]$RepoPath = "~/Anti-Bots",
    [string]$SshKeyPath = "",
    [switch]$SkipEnvPrepare,
    [switch]$SkipHealthCheck
)

$ErrorActionPreference = "Stop"
$vpsDir = $PSScriptRoot
$root = (Resolve-Path (Join-Path $vpsDir "..\..")).Path
$configFile = Join-Path $vpsDir "config.ps1"
$envFile = Join-Path $vpsDir ".env"

function Invoke-Ssh {
    param([string]$Command)
    $sshArgs = @()
    if ($SshKeyPath -and (Test-Path $SshKeyPath)) {
        $sshArgs += "-i", $SshKeyPath
    }
    $sshArgs += "${SshUser}@${VpsIp}", $Command
    & ssh @sshArgs
    if ($LASTEXITCODE -ne 0) { throw "SSH fallo: $Command" }
}

function Invoke-Scp {
    param([string]$Local, [string]$Remote)
    $scpArgs = @()
    if ($SshKeyPath -and (Test-Path $SshKeyPath)) {
        $scpArgs += "-i", $SshKeyPath
    }
    $scpArgs += $Local, "${SshUser}@${VpsIp}:$Remote"
    & scp @scpArgs
    if ($LASTEXITCODE -ne 0) { throw "SCP fallo: $Local -> $Remote" }
}

# Cargar config.ps1 si existe
if (Test-Path $configFile) {
    $cfg = & $configFile
    if (-not $VpsIp -and $cfg.VpsIp) { $VpsIp = $cfg.VpsIp }
    if ($cfg.SshUser) { $SshUser = $cfg.SshUser }
    if (-not $ApiDomain -and $cfg.ApiDomain) { $ApiDomain = $cfg.ApiDomain }
    if ($cfg.RepoPath) { $RepoPath = $cfg.RepoPath }
    if (-not $SshKeyPath -and $cfg.SshKeyPath) { $SshKeyPath = $cfg.SshKeyPath }
}

Write-Host ""
Write-Host "=== StreamShield VPS Deploy ===" -ForegroundColor Cyan
Write-Host ""

if (-not $VpsIp) {
    $VpsIp = (Read-Host "IP publica del VPS (ej. 95.217.x.x)").Trim()
}
if (-not $ApiDomain) {
    $ApiDomain = (Read-Host "Dominio API (ej. api.midominio.com)").Trim()
}
if ($VpsIp -match 'TU_IP|123\.456') {
    Write-Error "Usa la IP real del VPS, no el placeholder."
}

# Comprobar OpenSSH
foreach ($bin in @("ssh", "scp")) {
    if (-not (Get-Command $bin -ErrorAction SilentlyContinue)) {
        Write-Error "Falta $bin. En Windows: Configuracion -> Opciones -> OpenSSH Client."
    }
}

if (-not $SkipEnvPrepare) {
    & (Join-Path $vpsDir "prepare-vps-env.ps1") -ApiDomain $ApiDomain
}
if (-not (Test-Path $envFile)) {
    Write-Error "Falta $envFile. Ejecuta prepare-vps-env.ps1 primero."
}

Write-Host "Probando SSH a ${SshUser}@${VpsIp}..." -ForegroundColor Gray
Invoke-Ssh "echo OK"

$repoExpanded = $RepoPath -replace '^~', '/root'
if ($SshUser -ne 'root') {
    $repoExpanded = $RepoPath -replace '^~', "/home/$SshUser"
}

Write-Host "Preparando repo en el VPS..." -ForegroundColor Gray
$cloneCmd = "if [ -d '$repoExpanded/.git' ]; then cd '$repoExpanded' && git pull --ff-only; else git clone https://github.com/NlsG09201/Anti-Bots.git '$repoExpanded'; fi"
Invoke-Ssh $cloneCmd

Write-Host "Subiendo .env..." -ForegroundColor Gray
Invoke-Ssh "mkdir -p '$repoExpanded/deploy/vps'"
Invoke-Scp $envFile "$repoExpanded/deploy/vps/.env"

Write-Host "Arrancando Docker (puede tardar 2-5 min la primera vez)..." -ForegroundColor Gray
Invoke-Ssh "cd '$repoExpanded' && bash deploy/vps/setup-server.sh"

if (-not $SkipHealthCheck) {
    Write-Host ""
    Write-Host "Esperando HTTPS (60s)..." -ForegroundColor Gray
    $healthUrl = "https://${ApiDomain}/health"
    $ok = $false
    for ($i = 1; $i -le 12; $i++) {
        Start-Sleep -Seconds 5
        try {
            $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 15
            if ($r.StatusCode -eq 200) {
                Write-Host "Health OK: $($r.Content)" -ForegroundColor Green
                $ok = $true
                break
            }
        } catch {
            Write-Host "  intento $i/12..." -ForegroundColor DarkGray
        }
    }
    if (-not $ok) {
        Write-Host "Health aun no responde. Revisa DNS (A -> $VpsIp) y: ssh ${SshUser}@${VpsIp} 'cd $repoExpanded/deploy/vps && docker compose logs api'" -ForegroundColor Yellow
    }
}

$vercelBlock = @"
API_PROXY_TARGET=https://${ApiDomain}
NEXT_PUBLIC_WS_URL=wss://${ApiDomain}
"@
Set-Clipboard -Value $vercelBlock.Trim()

Write-Host "Ejecuta tambien: deploy\vercel-conectar.ps1 -ApiUrl https://${ApiDomain}" -ForegroundColor DarkGray

Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor Green
Write-Host "Vercel (copiado al portapapeles):" -ForegroundColor Cyan
Write-Host $vercelBlock
Write-Host ""
Write-Host "DNS: registro A  api  ->  $VpsIp  (o nombre completo $ApiDomain)" -ForegroundColor Gray
Write-Host "Neon: allowlist IP $VpsIp si esta activa" -ForegroundColor Gray
Write-Host "Twitch redirect: https://${ApiDomain}/api/v1/integrations/twitch/callback" -ForegroundColor Gray
Write-Host ""
