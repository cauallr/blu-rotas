param([string]$Netconvert = "netconvert")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "data\blumenau-centro.osm.xml"
$target = Join-Path $root "data\blumenau.net.xml"
$signalFile = Join-Path $root "data\blumenau-semaforos-simulados.json"
if (-not (Test-Path -LiteralPath $source)) { throw "OSM ausente: $source" }
$signals = Get-Content -LiteralPath $signalFile -Raw -Encoding UTF8 | ConvertFrom-Json
$signalIds = $signals.PSObject.Properties.Name -join ","
& $Netconvert --osm-files $source --output-file $target --geometry.remove --ramps.guess true --junctions.join true --tls.guess true --tls.guess-signals true --tls.default-type static --remove-edges.isolated true --no-turnarounds true --tls.set $signalIds
if ($LASTEXITCODE -ne 0) { throw "netconvert falhou com código $LASTEXITCODE" }
Write-Host "Rede SUMO criada: $target"
