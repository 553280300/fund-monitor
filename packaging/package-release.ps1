$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$artifact = Join-Path $projectRoot 'dist\FundMonitor.exe'
$release = Join-Path $projectRoot 'dist\FundMonitor-0.1.5-windows.zip'
$documents = @(
    'README.md',
    'docs\01-product-overview.md',
    'docs\02-quick-start-windows.md',
    'docs\03-asset-and-alert-configuration.md',
    'docs\04-notification-channels.md',
    'docs\05-troubleshooting.md',
    'docs\06-privacy-and-data.md',
    'docs\07-risk-disclaimer.md',
    'docs\release-checklist.md'
) | ForEach-Object { Join-Path $projectRoot $_ }

if (-not (Test-Path -LiteralPath $artifact)) {
    throw 'dist\FundMonitor.exe is missing. Run packaging\build.ps1 first.'
}
if (Test-Path -LiteralPath $release) {
    throw 'Release archive already exists; choose a new version instead of overwriting it.'
}

$releaseFiles = @($artifact) + $documents
Compress-Archive -Path $releaseFiles -DestinationPath $release -CompressionLevel Optimal
Write-Output "Created $release"
