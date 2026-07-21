# WHY: Keep the local reader up after login / resume without requiring Cursor.
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'venv\Scripts\python.exe'
$LogDir = Join-Path $Root 'logs'
$LogFile = Join-Path $LogDir 'autostart.log'
$HostAddr = '127.0.0.1'
$Port = 8770
$StatusUrl = "http://${HostAddr}:${Port}/api/status"

function Write-Log([string]$Message) {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Test-ServerUp {
    try {
        $response = Invoke-WebRequest -Uri $StatusUrl -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

if (-not (Test-Path $Python)) {
    Write-Log "SKIP: venv python missing at $Python"
    exit 1
}

if (Test-ServerUp) {
    Write-Log 'OK: server already running'
    exit 0
}

Write-Log 'START: launching uvicorn'
$argList = @(
    '-m', 'uvicorn',
    'sentence_reading.api.app:app',
    '--host', $HostAddr,
    '--port', "$Port"
)

$stdout = Join-Path $LogDir 'uvicorn.out.log'
$stderr = Join-Path $LogDir 'uvicorn.err.log'

Start-Process `
    -FilePath $Python `
    -ArgumentList $argList `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr | Out-Null

Start-Sleep -Seconds 2
if (Test-ServerUp) {
    Write-Log 'OK: server started'
    exit 0
}

Write-Log 'FAIL: server did not become ready'
exit 1
