param([string]$OutputPath)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path -Parent $projectRoot) 'blu-rotas-2.0.zip'
}
$archivePath = [System.IO.Path]::GetFullPath($OutputPath)
if (-not $archivePath.StartsWith((Split-Path -Parent $projectRoot), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'O ZIP deve ser salvo na pasta outputs, fora do projeto.'
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath
}
$archive = [System.IO.Compression.ZipFile]::Open($archivePath, [System.IO.Compression.ZipArchiveMode]::Create)
$script:files = 0

function Add-Files([string]$directory) {
    foreach ($file in Get-ChildItem -LiteralPath $directory -File -Force) {
        if ($file.Name -match '\.sqlite3$|\.pyc$|\.tsbuildinfo$|\.log$') { continue }
        if ($file.FullName -eq $archivePath) { continue }
        $relative = $file.FullName.Substring($projectRoot.Length + 1).Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $file.FullName, "blu-rotas/$relative",
            [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
        $script:files++
    }
    foreach ($child in Get-ChildItem -LiteralPath $directory -Directory -Force) {
        if ($child.Name -in @('node_modules', '__pycache__', '.pytest_cache', '.pytest-tmp', '.testtmp', '.venv')) { continue }
        if ($child.FullName -in @((Join-Path $projectRoot 'data\experiments'),
                                  (Join-Path $projectRoot 'data\cities'))) { continue }
        Add-Files $child.FullName
    }
}

try { Add-Files $projectRoot } finally { $archive.Dispose() }
Write-Host "Pacote criado com $script:files arquivos: $archivePath"
