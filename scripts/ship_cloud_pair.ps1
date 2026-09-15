# design/291 — thin wrapper: bash ship_release.sh is the source of truth.
param(
  [switch]$WithApk,
  [switch]$WithAdbInstall,
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$bash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $bash)) {
  Write-Error "Git bash not found: $bash"
  exit 1
}

$drive = $Root.Substring(0, 1).ToLower()
$rest = ($Root.Substring(2) -replace '\\', '/')
$rootUnix = "/$drive$rest"

$extra = ""
if ($WithApk) { $extra += "export WITH_APK=1; " }
if ($WithAdbInstall) { $extra += "export WITH_ADB_INSTALL=1; " }
if ($SkipVerify) { $extra += "export ASR_SHIP_SKIP_VERIFY=1; " }

# Only pass a simple cd + script path; no PowerShell-parsed bash conditionals.
$cmd = "${extra}cd '$rootUnix'; bash scripts/ship_release.sh"
Write-Host "design/291: bash scripts/ship_release.sh"
& $bash -lc $cmd
exit $LASTEXITCODE
