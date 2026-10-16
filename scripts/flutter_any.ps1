# design/403 - run any flutter command in mobile/ (same ProgramFiles(x86) fix as design/299).
# Never use an env-drive qualifier for that name. PowerShell parses it as a drive.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pf86 = 'ProgramFiles(x86)'
$cur = [Environment]::GetEnvironmentVariable($pf86, 'Process')
if ([string]::IsNullOrWhiteSpace($cur)) {
  [Environment]::SetEnvironmentVariable($pf86, 'C:\Program Files (x86)', 'Process')
}
Set-Location (Join-Path $Root "mobile")
& flutter @args
exit $LASTEXITCODE
