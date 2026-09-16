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

$extra = "export PYTHONUNBUFFERED=1; "
if ($WithApk) { $extra += "export WITH_APK=1; " }
if ($WithAdbInstall) { $extra += "export WITH_ADB_INSTALL=1; " }
if ($SkipVerify) { $extra += "export ASR_SHIP_SKIP_VERIFY=1; " }

# stdbuf keeps phase lines visible. Do not start a second ship from this wrapper.
$ship = "if command -v stdbuf >/dev/null 2>&1; then stdbuf -oL -eL bash scripts/ship_release.sh; else bash scripts/ship_release.sh; fi"
$cmd = "${extra}cd '$rootUnix'; $ship"
Write-Host "design/291: bash scripts/ship_release.sh"

$stamp = [guid]::NewGuid().ToString("n")
$outLog = Join-Path $env:TEMP ("asr-ship-" + $stamp + ".out.log")
$errLog = Join-Path $env:TEMP ("asr-ship-" + $stamp + ".err.log")
$proc = Start-Process -FilePath $bash -ArgumentList @("-lc", $cmd) -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog

function Read-NewText([string]$path, [ref]$offset) {
  if (-not (Test-Path $path)) { return "" }
  $fs = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
  try {
    if ($offset.Value -ge $fs.Length) { return "" }
    $null = $fs.Seek($offset.Value, [IO.SeekOrigin]::Begin)
    $buf = New-Object byte[] ($fs.Length - $offset.Value)
    $n = $fs.Read($buf, 0, $buf.Length)
    $offset.Value += $n
    return [Text.Encoding]::UTF8.GetString($buf, 0, $n)
  } finally {
    $fs.Dispose()
  }
}

$outAt = 0
$errAt = 0
while ($proc -and -not $proc.HasExited) {
  $chunk = (Read-NewText $outLog ([ref]$outAt)) + (Read-NewText $errLog ([ref]$errAt))
  if ($chunk) { Write-Host $chunk }
  Start-Sleep -Seconds 2
  try { $proc.Refresh() } catch { break }
}
$rest = (Read-NewText $outLog ([ref]$outAt)) + (Read-NewText $errLog ([ref]$errAt))
if ($rest) { Write-Host $rest }

$text = ""
foreach ($path in @($outLog, $errLog)) {
  if (Test-Path $path) { $text += [IO.File]::ReadAllText($path) }
}
$code = 1
if ($proc) {
  try { $proc.Refresh() } catch { }
  if ($null -ne $proc.ExitCode) { $code = [int]$proc.ExitCode }
}

if ($text -match "ship_release OK") {
  exit 0
}
if ($text -match "asr-sentence-reading-worker" -and $text -notmatch "ship_release OK") {
  Write-Host "design/304: ship log ended after worker; verify only, no second deploy"
  python scripts/verify_live_status.py --require-azure-layout --min-pipeline rich-v20
  exit $LASTEXITCODE
}
exit $code
