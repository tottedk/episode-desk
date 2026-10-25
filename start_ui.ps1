<#
.SYNOPSIS
  Start the episode desk on 127.0.0.1 and open a browser.

.DESCRIPTION
  Run this by hand. Python stays in this window. Close the window to stop
  the server. The page also has a Stop server button. This script does not
  install a service or a scheduled task.

.PARAMETER DryRun
  Write briefs and do not start the pipeline.

.PARAMETER Port
  Loopback port. Default 47221.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ui.ps1

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ui.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [int]$Port = 47221
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-not $PSScriptRoot) {
    Write-Host "Run this file with: powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ui.ps1"
    exit 1
}

Set-Location -LiteralPath $PSScriptRoot

try { $Host.UI.RawUI.WindowTitle = "Episode desk" } catch {}

if ($Port -lt 1 -or $Port -gt 65535) {
    Write-Host "Port must be between 1 and 65535."
    exit 1
}

$configPath = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Host "Missing config.json. Copy config.example.json to config.json and set your paths."
    exit 1
}

function Test-Python310 {
    param(
        [string]$Exe,
        [string[]]$Prefix
    )
    try {
        & $Exe @Prefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$pythonCmd = $null
$pythonPrefix = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python310 -Exe "py" -Prefix @("-3")) {
        $pythonCmd = "py"
        $pythonPrefix = @("-3")
    }
}
if (-not $pythonCmd -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python310 -Exe "python" -Prefix @()) {
        $pythonCmd = "python"
        $pythonPrefix = @()
    }
}
if (-not $pythonCmd) {
    Write-Host "Python 3.10+ was not found on PATH."
    exit 1
}

$url = "http://127.0.0.1:$Port/"
$serverArgs = @()
$serverArgs += $pythonPrefix
$serverArgs += "-u"
$serverArgs += (Join-Path $PSScriptRoot "server.py")
$serverArgs += "--port"
$serverArgs += "$Port"
if ($DryRun) {
    $serverArgs += "--dry-run"
}

$openerSource = @'
$ErrorActionPreference = "Continue"
$deadline = (Get-Date).AddSeconds(20)
$url = "__URL__"
$port = __PORT__
while ((Get-Date) -lt $deadline) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $tcp.BeginConnect("127.0.0.1", $port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(300)) {
            $tcp.EndConnect($iar)
            Start-Process $url
            exit 0
        }
    } catch {
    } finally {
        if ($tcp) { $tcp.Close() }
    }
    Start-Sleep -Milliseconds 250
}
exit 1
'@
$openerSource = $openerSource.Replace("__URL__", $url).Replace("__PORT__", "$Port")
$encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($openerSource))

Write-Host "Episode desk: $url"
if ($DryRun) {
    Write-Host "Dry run: briefs are written and the pipeline is not started."
}
Write-Host "Close this window to stop the server."

$opener = $null
try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $encoded"
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $opener = [System.Diagnostics.Process]::Start($psi)
} catch {
    Write-Host "Could not open a browser automatically. Open this URL: $url"
}

$code = 0
try {
    & $pythonCmd @serverArgs
    if ($null -ne $LASTEXITCODE) {
        $code = $LASTEXITCODE
    }
} finally {
    if ($opener -and -not $opener.HasExited) {
        try { $opener.Kill() } catch {}
    }
}

Write-Host "Server stopped."
exit $code
