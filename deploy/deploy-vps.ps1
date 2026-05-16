# Atajo: despliegue VPS completo (o solo .env con -PrepareOnly)
param(
    [switch]$PrepareOnly
)

if ($PrepareOnly) {
    & (Join-Path $PSScriptRoot "vps\prepare-vps-env.ps1")
} else {
    & (Join-Path $PSScriptRoot "vps\vps-deploy.ps1") @args
}
