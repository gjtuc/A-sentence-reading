# design/296 — Windows commit uses PowerShell git commit -m only.
param(
  [Parameter(Mandatory = $true)]
  [string]$Message,
  [string]$Body = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($Message.Trim().Length -lt 8) {
  Write-Error "design/296: commit message too short"
  exit 2
}
if ($Message -match '<<' -or $Body -match '<<') {
  Write-Error "design/296: do not pass a here-doc marker; use -Message and -Body"
  exit 2
}

if ($Body.Trim().Length -gt 0) {
  & git commit -m $Message -m $Body
} else {
  & git commit -m $Message
}
exit $LASTEXITCODE
