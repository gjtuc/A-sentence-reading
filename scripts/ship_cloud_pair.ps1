# design/290 — Cloud Run pair ship (no parallel APK). Success = verify + image match.
param(
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Test-ApkBuildRunning {
  $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $cmd = [string]$_.CommandLine
      $cmd -match 'build_release_apk\.ps1' -or
      ($cmd -match 'flutter(\.bat)?' -and $cmd -match 'build apk')
    }
  return [bool]$procs
}

if (-not $env:ASR_SHIP_ALLOW_PARALLEL_APK -and (Test-ApkBuildRunning)) {
  Write-Error "design/290: flutter/APK build running — refuse cloud ship (set ASR_SHIP_ALLOW_PARALLEL_APK=1 to override)"
  exit 2
}

$bash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $bash)) {
  Write-Error "Git bash not found: $bash"
  exit 1
}

$drive = $Root.Substring(0, 1).ToLower()
$rest = ($Root.Substring(2) -replace '\\', '/')
$rootUnix = "/$drive$rest"
$envFile = "/c/Users/user/Desktop/.cursor/gc-home/gc_automation.env"

# Single-quoted -lc body so PowerShell does not parse [, &&, or python quotes.
$bashLc = @'
set -a
if [ -f '"$envFile"' ]; then source '"$envFile"'; fi
set +a
cd '"$rootUnix"'
bash scripts/deploy_cloud_run_pair.sh
'@
# Expand paths into the bash script without PS parsing bash syntax.
$bashLc = "set -a; if [ -f '$envFile' ]; then source '$envFile'; fi; set +a; cd '$rootUnix'; bash scripts/deploy_cloud_run_pair.sh"

Write-Host "design/290: deploy_cloud_run_pair.sh ..."
& $bash -lc $bashLc
if ($LASTEXITCODE -ne 0) {
  Write-Error "pair deploy failed rc=$LASTEXITCODE (see .tmp_pair_deploy.log)"
  exit $LASTEXITCODE
}

if ($SkipVerify) {
  Write-Host "design/290: SkipVerify — done"
  exit 0
}

$verLine = Select-String -Path "src\sentence_reading\api\app.py" -Pattern 'version="([^"]+)"' | Select-Object -First 1
$ver = $verLine.Matches[0].Groups[1].Value
Write-Host "design/290: verify_live_status --expect $ver"
& python scripts/verify_live_status.py --require-azure-layout --min-pipeline rich-v20 --expect $ver
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& python scripts/check_api_worker_images_match.py
if ($LASTEXITCODE -ne 0) {
  Write-Error "design/290: API/worker image mismatch after pair"
  exit 1
}

Write-Host "design/290: ship_cloud_pair OK"
exit 0
