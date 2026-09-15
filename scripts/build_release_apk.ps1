# design/287/289/291 — release APK helper (default machine caches; opt-in same-drive).
param(
  [switch]$SkipCopy,
  [switch]$WarmCaches,
  [switch]$SameDriveCache
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Mobile = Join-Path $Root "mobile"
$GradleProps = Join-Path $Mobile "android\gradle.properties"
$ApkOut = Join-Path $Mobile "build\app\outputs\flutter-apk\app-release.apk"
$ApkCopy = Join-Path $Root "data\sentence-reading-latest.apk"
$Gradlew = Join-Path $Mobile "android\gradlew.bat"
$CacheRoot = Join-Path $Root ".cache\apk-tooling"
$PubCache = Join-Path $CacheRoot "pub-cache"
$GradleHome = Join-Path $CacheRoot "gradle-user-home"
$script:UsedSameDrive = $false

function Enable-SameDriveCache {
  New-Item -ItemType Directory -Force -Path $PubCache, $GradleHome | Out-Null
  $env:PUB_CACHE = $PubCache
  $env:GRADLE_USER_HOME = $GradleHome
  $script:UsedSameDrive = $true
  Write-Host "design/291: SameDriveCache PUB_CACHE=$env:PUB_CACHE"
}

function Disable-SameDriveCache {
  Remove-Item Env:PUB_CACHE -ErrorAction SilentlyContinue
  Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue
  $script:UsedSameDrive = $false
  Write-Host "design/291: using machine default Pub/Gradle caches"
}

function Invoke-FlutterApk {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $out = & flutter build apk --release 2>&1 | ForEach-Object { "$_" } | Out-String
    return @{ Log = $out; Code = [int]$LASTEXITCODE }
  } finally {
    $ErrorActionPreference = $prev
  }
}

function Test-FreshApk([datetime]$started) {
  if (-not (Test-Path $ApkOut)) { return $false }
  $mtime = (Get-Item $ApkOut).LastWriteTime
  return ($mtime -ge $started.AddSeconds(-60))
}

function Test-ApkOk([hashtable]$r, [datetime]$started) {
  if (-not (Test-Path $ApkOut)) { return $false }
  if ($r.Code -eq 0) { return $true }
  if ($r.Log -match 'Built build\\app\\outputs\\flutter-apk\\app-release\.apk') { return $true }
  if (Test-FreshApk $started) {
    Write-Host "design/289: treating fresh APK artifact as success (exit=$($r.Code))"
    return $true
  }
  return $false
}

function Test-KernelSnapshotFail([string]$log) {
  return $log -match 'kernel_snapshot_program' -or
    $log -match 'compileFlutterBuildRelease'
}

function Ensure-KotlinIncrementalOff {
  $text = Get-Content -Raw -Path $GradleProps
  if ($text -notmatch 'kotlin\.incremental=false') {
    Add-Content -Path $GradleProps -Value "`r`n# design/287`r`nkotlin.incremental=false`r`nkotlin.incremental.java=false`r`n"
    Write-Host "design/287: pinned kotlin.incremental=false"
  }
}

function Stop-GradleDaemons {
  if (Test-Path $Gradlew) {
    & $Gradlew --stop 2>$null | Out-Null
  }
}

function Test-IncrementalCacheFail([string]$log) {
  return $log -match 'Could not close incremental caches' -or
    $log -match 'different roots:'
}

function Clear-MobileBuildCaches {
  Stop-GradleDaemons
  Start-Sleep -Seconds 2
  Remove-Item -Recurse -Force (Join-Path $Mobile "build") -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force (Join-Path $Mobile "android\.gradle") -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force (Join-Path $Mobile "android\app\build") -ErrorAction SilentlyContinue
}

Ensure-KotlinIncrementalOff
Set-Location $Mobile
Stop-GradleDaemons

if ($SameDriveCache) {
  Enable-SameDriveCache
} else {
  Disable-SameDriveCache
}

if ($WarmCaches) {
  Write-Host "design/289: WarmCaches - flutter pub get"
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & flutter pub get 2>&1 | ForEach-Object { Write-Host $_ }
  } finally {
    $ErrorActionPreference = $prev
  }
}

$started = Get-Date
Write-Host "flutter build apk --release ..."
$r1 = Invoke-FlutterApk
Write-Host $r1.Log
$ok = Test-ApkOk $r1 $started

if (-not $ok -and (Test-IncrementalCacheFail $r1.Log)) {
  Write-Host "design/287: incremental-cache failure - wipe build and retry once"
  Clear-MobileBuildCaches
  $started = Get-Date
  $r2 = Invoke-FlutterApk
  Write-Host $r2.Log
  $ok = Test-ApkOk $r2 $started
}

# design/291 R3 — SameDrive cold cache often breaks kernel_snapshot; fall back once.
if (-not $ok -and $script:UsedSameDrive -and (Test-KernelSnapshotFail $r1.Log)) {
  Write-Host "design/291: kernel_snapshot fail on SameDriveCache - fallback to machine caches"
  Disable-SameDriveCache
  Clear-MobileBuildCaches
  $started = Get-Date
  $r3 = Invoke-FlutterApk
  Write-Host $r3.Log
  $ok = Test-ApkOk $r3 $started
}

if (-not $ok) {
  Write-Error "APK build failed"
  exit 1
}

Write-Host "OK: $ApkOut"
if (-not $SkipCopy) {
  New-Item -ItemType Directory -Force -Path (Split-Path $ApkCopy) | Out-Null
  Copy-Item -Force $ApkOut $ApkCopy
  Write-Host "Copied: $ApkCopy"
}
exit 0
