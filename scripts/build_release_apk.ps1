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

function Read-ApkLog([string]$path) {
  if (-not (Test-Path $path)) { return "" }
  try {
    return [IO.File]::ReadAllText($path)
  } catch {
    return ""
  }
}

function Stop-ProcessTree([int]$processId) {
  if ($processId -le 0) { return }
  & taskkill.exe /F /T /PID $processId 2>$null | Out-Null
}

function Test-GradleDaemonRunning {
  $hit = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'GradleDaemon' }
  return $null -ne $hit
}

function Wait-GradleDaemonsGone {
  # design/300 - --stop must finish before the next flutter build starts.
  Stop-GradleDaemons
  for ($i = 0; $i -lt 15; $i++) {
    if (-not (Test-GradleDaemonRunning)) {
      Write-Host "design/300: GradleDaemon gone"
      return
    }
    Write-Host "design/300: waiting for GradleDaemon to exit"
    Start-Sleep -Seconds 2
  }
  Stop-GradleDaemons
  Start-Sleep -Seconds 2
}

function Invoke-FlutterApk {
  # design/298 - cmd /c so Gradle/JVM stderr is not a PowerShell error record.
  # design/300 - do not wait forever after BUILD FAILED or a stable APK file.
  $log = Join-Path $env:TEMP ("asr-apk-" + [guid]::NewGuid().ToString("n") + ".log")
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $proc = $null
  try {
    $arg = '/c flutter build apk --release > "' + $log + '" 2>&1'
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList $arg -WorkingDirectory $Mobile -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddMinutes(25)
    $lastLen = -1
    $failIdle = 0
    $apkIdle = 0
    $apkLen = -1
    while ($proc -and -not $proc.HasExited) {
      if ((Get-Date) -gt $deadline) {
        Write-Host "design/300: apk build deadline - stop hung flutter"
        Stop-ProcessTree $proc.Id
        break
      }
      Start-Sleep -Seconds 5
      try { $proc.Refresh() } catch { break }
      $len = 0
      if (Test-Path $log) { $len = (Get-Item $log).Length }
      $text = Read-ApkLog $log
      $grew = ($len -ne $lastLen)
      $lastLen = $len
      if ($grew) {
        $failIdle = 0
      } elseif ($text -match 'BUILD FAILED' -or $text -match 'kernel_snapshot_program' -or $text -match 'compileFlutterBuildRelease') {
        $failIdle += 1
        if ($failIdle -ge 4) {
          Write-Host "design/300: failure log idle - stop hung flutter"
          Stop-ProcessTree $proc.Id
          break
        }
      }
      if (Test-FreshApk $script:ApkStarted) {
        $nowLen = (Get-Item $ApkOut).Length
        if ($nowLen -gt 1000000 -and $nowLen -eq $apkLen) {
          $apkIdle += 1
        } else {
          $apkIdle = 0
          $apkLen = $nowLen
        }
        if ($apkIdle -ge 3) {
          Write-Host "design/300: APK file stable - stop hung flutter"
          Stop-ProcessTree $proc.Id
          break
        }
      }
    }
    if ($proc -and -not $proc.HasExited) {
      try { $proc.WaitForExit(15000) | Out-Null } catch {}
    }
    $code = 1
    if ($proc -and $proc.HasExited) { $code = [int]$proc.ExitCode }
    return @{ Log = (Read-ApkLog $log); Code = $code }
  } finally {
    $ErrorActionPreference = $prev
    Remove-Item $log -ErrorAction SilentlyContinue
  }
}

function Test-ApkBuildAlreadyRunning {
  $hit = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'flutter(\.bat)?\s+build\s+apk' }
  return $null -ne $hit
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
    $log -match 'compileFlutterBuildRelease' -or
    $log -match 'Invalid depfile'
}

function Clear-FlutterSnapshot {
  Wait-GradleDaemonsGone
  Remove-Item -Recurse -Force (Join-Path $Mobile ".dart_tool\flutter_build") -ErrorAction SilentlyContinue
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
  Wait-GradleDaemonsGone
  Remove-Item -Recurse -Force (Join-Path $Mobile "build") -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force (Join-Path $Mobile "android\.gradle") -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force (Join-Path $Mobile "android\app\build") -ErrorAction SilentlyContinue
}

Ensure-KotlinIncrementalOff
Set-Location $Mobile
if (Test-ApkBuildAlreadyRunning) {
  Write-Error "design/298: refuse APK build - flutter build apk already running"
  exit 2
}
Wait-GradleDaemonsGone

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
$script:ApkStarted = $started
Write-Host "flutter build apk --release ..."
$r1 = Invoke-FlutterApk
Write-Host $r1.Log
$ok = Test-ApkOk $r1 $started

if (-not $ok -and (Test-IncrementalCacheFail $r1.Log)) {
  Write-Host "design/287: incremental-cache failure - wipe build and retry once"
  Clear-MobileBuildCaches
  $started = Get-Date
  $script:ApkStarted = $started
  $r2 = Invoke-FlutterApk
  Write-Host $r2.Log
  $ok = Test-ApkOk $r2 $started
}

# design/298 - snapshot/depfile fail retries once on the default cache too.
if (-not $ok -and (Test-KernelSnapshotFail $r1.Log)) {
  Write-Host "design/298: snapshot or compile fail - wipe flutter_build and retry once"
  Clear-FlutterSnapshot
  $started = Get-Date
  $script:ApkStarted = $started
  $r2s = Invoke-FlutterApk
  Write-Host $r2s.Log
  $ok = Test-ApkOk $r2s $started
}

# design/291 R3 - SameDrive cold cache often breaks kernel_snapshot; fall back once.
if (-not $ok -and $script:UsedSameDrive -and (Test-KernelSnapshotFail $r1.Log)) {
  Write-Host "design/291: kernel_snapshot fail on SameDriveCache - fallback to machine caches"
  Disable-SameDriveCache
  Clear-MobileBuildCaches
  $started = Get-Date
  $script:ApkStarted = $started
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
