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
$url = "http://127.0.0.1:$Port/"
$arguments = @('-m', 'knowflow.web', '--port', "$Port")
if ($Refresh) { $arguments += '--refresh' }

if ($NoBrowser) {
    & $pythonPath @arguments
    exit $LASTEXITCODE
}

# Start the server as a child of this window, then open the browser once the
# port answers. `python -m knowflow.web --open` only works when the process owns
# an interactive desktop, so the launcher opens the page itself.
$server = Start-Process -FilePath $pythonPath -ArgumentList $arguments -NoNewWindow -PassThru
$opened = $false
for ($attempt = 0; $attempt -lt 240; $attempt++) {
    if ($server.HasExited) { break }
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect('127.0.0.1', $Port)
        $client.Close()
        try {
            Start-Process $url
            $opened = $true
        } catch {
            Write-Host "打不开默认浏览器，请手动访问：$url"
        }
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $opened -and -not $server.HasExited) {
    Write-Host "服务已启动但浏览器未自动打开，请手动访问：$url"
}
Wait-Process -Id $server.Id
exit $server.ExitCode
