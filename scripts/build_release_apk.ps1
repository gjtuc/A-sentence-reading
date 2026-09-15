# design/287 + 289 — reliable Windows release APK (D5 caches · artifact-truth success).
param(
  [switch]$SkipCopy,
  [switch]$WarmCaches
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Mobile = Join-Path $Root "mobile"
$GradleProps = Join-Path $Mobile "android\gradle.properties"
$ApkOut = Join-Path $Mobile "build\app\outputs\flutter-apk\app-release.apk"
$ApkCopy = Join-Path $Root "data\sentence-reading-latest.apk"
$Gradlew = Join-Path $Mobile "android\gradlew.bat"
# D5 — Pub/Gradle on same drive as repo (D:) so Kotlin incremental maps never see C: vs D:.
$CacheRoot = Join-Path $Root ".cache\apk-tooling"
$PubCache = Join-Path $CacheRoot "pub-cache"
$GradleHome = Join-Path $CacheRoot "gradle-user-home"
New-Item -ItemType Directory -Force -Path $PubCache, $GradleHome | Out-Null
$env:PUB_CACHE = $PubCache
$env:GRADLE_USER_HOME = $GradleHome

function Invoke-FlutterApk {
  # Flutter prints JVM warnings on stderr; PS Stop mode must not treat them as fatals.
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
  # design/289 S3 — artifact truth: accept if written near/after this run started.
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
Write-Host "design/287 D5: PUB_CACHE=$env:PUB_CACHE"
Write-Host "design/287 D5: GRADLE_USER_HOME=$env:GRADLE_USER_HOME"

if ($WarmCaches) {
  Write-Host "design/289: WarmCaches — flutter pub get …"
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
  Write-Host "design/287: incremental-cache failure — wipe build and retry once"
  Clear-MobileBuildCaches
  $started = Get-Date
  $r2 = Invoke-FlutterApk
  Write-Host $r2.Log
  $ok = Test-ApkOk $r2 $started
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
