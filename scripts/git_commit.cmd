@echo off
rem design/298 - bypass execution policy. Do not call git_commit.ps1 with powershell -File.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git_commit.ps1" %*
exit /b %ERRORLEVEL%
