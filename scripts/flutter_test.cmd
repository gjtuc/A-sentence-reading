@echo off
rem design/299 - bypass execution policy. Do not assign ProgramFiles(x86) with an env-drive qualifier.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flutter_test.ps1" %*
exit /b %ERRORLEVEL%
