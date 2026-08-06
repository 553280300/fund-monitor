$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$spec = Join-Path $PSScriptRoot 'fund_monitor.spec'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Project virtual environment is missing. Create .venv and install dependencies first.'
}

& $python -m PyInstaller --noconfirm $spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$artifact = Join-Path $projectRoot 'dist\FundMonitor.exe'
if (-not (Test-Path -LiteralPath $artifact)) {
    throw 'Build finished without dist\FundMonitor.exe.'
}

Write-Output "Built $artifact"
