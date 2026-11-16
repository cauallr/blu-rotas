param([ValidateRange(1024, 65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($PSBoundParameters.ContainsKey('Port')) {
    & (Join-Path $projectRoot 'iniciar.ps1') -Port $Port
} else {
    & (Join-Path $projectRoot 'iniciar.ps1')
}
