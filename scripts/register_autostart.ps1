# WHY: 패키지 `sentence_reading.autostart`로 위임 — pip install 훅과 동일 등록.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Python = 'python'
}
& $Python -m sentence_reading.autostart register
exit $LASTEXITCODE
