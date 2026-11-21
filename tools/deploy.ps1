param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Source = Join-Path $PSScriptRoot "..\Jiny"
$Target = Join-Path $PSScriptRoot "..\..\_forever_\Interface\AddOns\Jiny"

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    Write-Error "No se encontró el directorio de origen del addon: $Source"
    exit 1
}

$ResolvedSource = [System.IO.Path]::GetFullPath($Source)
$ResolvedTarget = [System.IO.Path]::GetFullPath($Target)

if (-not $Force) {
    Write-Host "Origen : $ResolvedSource"
    Write-Host "Destino: $ResolvedTarget"
    $confirm = Read-Host "¿Deseas sincronizar Jiny en _forever_? (escribe 'S' o 'Y' para continuar)"
    if ($confirm -notin @("s", "S", "y", "Y", "si", "SI", "sí", "SÍ", "yes", "YES")) {
        Write-Host "Despliegue cancelado por el usuario."
        exit 0
    }
}

New-Item -ItemType Directory -Path $ResolvedTarget -Force | Out-Null

& robocopy $Source $Target /MIR /XF *.svg /NFL /NDL /NJH /NJS
$rc = $LASTEXITCODE

if ($rc -lt 8) {
    Write-Host "Despliegue completado correctamente (robocopy exit code: $rc)."
    exit 0
}

Write-Error "Error al desplegar con robocopy (exit code: $rc)."
exit $rc
