# design/299 - flutter test dies when ProgramFiles(x86) is unset.
# Never use an env-drive qualifier for that name. PowerShell parses it as a drive.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pf86 = 'ProgramFiles(x86)'
$cur = [Environment]::GetEnvironmentVariable($pf86, 'Process')
if ([string]::IsNullOrWhiteSpace($cur)) {
  [Environment]::SetEnvironmentVariable($pf86, 'C:\Program Files (x86)', 'Process')
}
Set-Location (Join-Path $Root "mobile")
& flutter test @args
exit $LASTEXITCODE
