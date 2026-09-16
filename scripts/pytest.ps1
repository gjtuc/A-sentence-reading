# design/303 — pin this checkout. A bare pytest can import the Desktop tree.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
& python -m pytest @args
exit $LASTEXITCODE
