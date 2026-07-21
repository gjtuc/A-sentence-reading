# WHY: Register per-user Task Scheduler jobs (no admin) for login + unlock + sleep resume.
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$EnsureScript = Join-Path $PSScriptRoot 'ensure_server.ps1'
$TaskName = 'A-sentence-reading Ensure Server'
$UserId = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path $EnsureScript)) {
    throw "Missing ensure script: $EnsureScript"
}

$queryEscaped = [System.Security.SecurityElement]::Escape(@'
<QueryList><Query Id="0" Path="System"><Select Path="System">*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and (EventID=1)]]</Select></Query></QueryList>
'@)

$xmlPath = Join-Path $env:TEMP 'a-sentence-reading-autostart-task.xml'
@"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Start A-sentence-reading local server if it is not already up (login / unlock / resume).</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$UserId</UserId>
    </LogonTrigger>
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled>
      <StateChange>SessionUnlock</StateChange>
      <UserId>$UserId</UserId>
    </SessionStateChangeTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>$queryEscaped</Subscription>
      <Delay>PT10S</Delay>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$UserId</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$EnsureScript"</Arguments>
      <WorkingDirectory>$Root</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@ | Set-Content -Path $xmlPath -Encoding Unicode

$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
cmd.exe /c "schtasks /Delete /TN `"$TaskName`" /F" | Out-Null
cmd.exe /c "schtasks /Delete /TN `"A-sentence-reading Ensure Server On Resume`" /F" | Out-Null
$ErrorActionPreference = $prevEap

$createOut = cmd.exe /c "schtasks /Create /TN `"$TaskName`" /XML `"$xmlPath`" /F"
if ($LASTEXITCODE -ne 0) {
    throw "Task registration failed: $createOut"
}
Remove-Item $xmlPath -Force -ErrorAction SilentlyContinue

Write-Host "Registered: $TaskName"
Write-Host "  Triggers: AtLogOn + SessionUnlock + resume-from-sleep"
Write-Host "Ensure script: $EnsureScript"
