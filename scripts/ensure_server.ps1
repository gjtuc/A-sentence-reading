# design/138 — ensure no longer starts local uvicorn; unregister leftover task.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
& $Python -m sentence_reading.autostart unregister
Write-Host "design/138: local ensure removed — use Live Cloud Run."
