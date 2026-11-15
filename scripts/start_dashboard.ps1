param(
    [int]$Port = 8765,
    [switch]$Refresh,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host 'Python environment not found. Run these commands in KnowFlow first:'
    Write-Host '  python -m venv .venv'
    Write-Host '  .\.venv\Scripts\python.exe -m pip install -e ".[dev]"'
    exit 1
}
$env:PYTHONUTF8 = '1'
$arguments = @('-m', 'knowflow.web', '--port', "$Port")
if ($Refresh) { $arguments += '--refresh' }
if (-not $NoBrowser) { $arguments += '--open' }
& $pythonPath @arguments
exit $LASTEXITCODE
