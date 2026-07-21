# WHY: 패키지 `sentence_reading.autostart`로 위임 — pip 설치물과 동일 경로.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Python = 'python'
}
& $Python -m sentence_reading.autostart ensure
exit $LASTEXITCODE
