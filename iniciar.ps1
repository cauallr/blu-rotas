param(
    [string]$SumoBinary = $env:SUMO_BINARY,
    [ValidateRange(1024, 65535)][int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$venvSumo = Join-Path $projectRoot '.venv\Scripts\sumo.exe'
$portablePython = Join-Path $projectRoot '..\..\work\python-embed\python.exe'
$portableSumo = Join-Path $projectRoot '..\..\work\sumo\sumo-win64-1.28.0\bin\sumo.exe'

if (Test-Path -LiteralPath $venvPython) {
    $pythonExecutable = (Resolve-Path -LiteralPath $venvPython).Path
} elseif (Test-Path -LiteralPath $portablePython) {
    $pythonExecutable = (Resolve-Path -LiteralPath $portablePython).Path
} else {
    throw 'Python não preparado. Siga a seção "Executar no Windows" do README.md para criar .venv.'
}

if (-not $SumoBinary -and (Test-Path -LiteralPath $portableSumo)) {
    $SumoBinary = (Resolve-Path -LiteralPath $portableSumo).Path
}
if (-not $SumoBinary) {
    $installedSumo = Get-Command sumo.exe -ErrorAction SilentlyContinue
    if ($installedSumo) { $SumoBinary = $installedSumo.Source }
}
if (-not $SumoBinary -and (Test-Path -LiteralPath $venvSumo)) {
    $SumoBinary = $venvSumo
}
if (-not $SumoBinary -or -not (Test-Path -LiteralPath $SumoBinary)) {
    throw 'SUMO não encontrado. Defina $env:SUMO_BINARY com o caminho completo de sumo.exe; veja README.md.'
}

$env:SUMO_BINARY = (Resolve-Path -LiteralPath $SumoBinary).Path
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    throw 'Interface compilada ausente. Na pasta frontend, execute npm ci e npm run build.'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'data\blumenau.net.xml'))) {
    throw 'Malha SUMO ausente. Veja a seção Recriar a malha no README.md.'
}
function Test-BluServer([int]$CandidatePort) {
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$CandidatePort/api/status" -TimeoutSec 2
        return $null -ne $status.ready
    } catch { return $false }
}
if (Test-BluServer $Port) {
    Write-Host "BLU-ROTAS já está aberto em http://127.0.0.1:$Port/" -ForegroundColor Green
    return
}
if (-not $PSBoundParameters.ContainsKey('Port')) {
    $available = $false
    foreach ($candidate in 8000..8010) {
        $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $candidate)
        try {
            $probe.Start()
            $Port = $candidate
            $available = $true
            break
        } catch [System.Net.Sockets.SocketException] {
            continue
        } finally {
            $probe.Stop()
        }
    }
    if (-not $available) {
        throw 'As portas 8000 a 8010 estão ocupadas. Use .\iniciar.ps1 -Port 8011 após liberar uma porta.'
    }
}
Write-Host "BLU-ROTAS: servidor em http://127.0.0.1:$Port/" -ForegroundColor Cyan
Write-Host "Abra este endereço no navegador: http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host 'Deixe esta janela aberta enquanto usa o jogo. Ctrl+C encerra o servidor.'
& $pythonExecutable -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) {
    throw "O servidor encerrou com o código $LASTEXITCODE."
}
