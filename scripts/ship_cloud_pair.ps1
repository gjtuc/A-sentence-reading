# design/291 — thin wrapper: bash ship_release.sh is the source of truth.
# design/304 — line-buffered log; a stall after the worker is verify-only.
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

$lines = @("export PYTHONUNBUFFERED=1")
if ($WithApk) { $lines += "export WITH_APK=1" }
if ($WithAdbInstall) { $lines += "export WITH_ADB_INSTALL=1" }
if ($SkipVerify) { $lines += "export ASR_SHIP_SKIP_VERIFY=1" }
$lines += "cd '$rootUnix'"
# stdbuf keeps phase lines visible. Do not start a second ship from this wrapper.
$lines += "if command -v stdbuf >/dev/null 2>&1; then"
$lines += "  exec stdbuf -oL -eL bash scripts/ship_release.sh"
$lines += "else"
$lines += "  exec bash scripts/ship_release.sh"
$lines += "fi"
Write-Host "design/291: bash scripts/ship_release.sh"

$stamp = [guid]::NewGuid().ToString("n")
$outLog = Join-Path $env:TEMP ("asr-ship-" + $stamp + ".out.log")
$shWin = Join-Path $env:TEMP ("asr-ship-" + $stamp + ".sh")
$shUnix = "/c/Users/user/AppData/Local/Temp/asr-ship-" + $stamp + ".sh"
$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($shWin, (($lines -join "`n") + "`n"), $utf8)
# Call operator inherits the console. A detached process left remote-https waiting.
$arg = "bash $shUnix"
& $bash -lc $arg 2>&1 | ForEach-Object {
  $line = $_.ToString()
  Add-Content -Path $outLog -Value $line -Encoding utf8
  Write-Host $line
}
$code = $LASTEXITCODE
$text = ""
if (Test-Path $outLog) { $text = [IO.File]::ReadAllText($outLog) }

if ($text -match "ship_release OK") {
  exit 0
}
if ($text -match "asr-sentence-reading-worker" -and $text -notmatch "ship_release OK") {
  Write-Host "design/304: ship log ended after worker; verify only, no second deploy"
  python scripts/verify_live_status.py --require-azure-layout --min-pipeline rich-v20
  exit $LASTEXITCODE
}
exit $code
