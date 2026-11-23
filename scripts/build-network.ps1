param([string]$Netconvert = "netconvert")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "data\blumenau-centro.osm.xml"
$target = Join-Path $root "data\blumenau.net.xml"
if (-not (Test-Path -LiteralPath $source)) { throw "OSM ausente: $source" }
& $Netconvert --osm-files $source --output-file $target --geometry.remove --ramps.guess true --junctions.join true --tls.guess true --tls.guess-signals true --tls.default-type static --remove-edges.isolated true --no-turnarounds true
if ($LASTEXITCODE -ne 0) { throw "netconvert falhou com código $LASTEXITCODE" }
Write-Host "Rede SUMO criada: $target"
