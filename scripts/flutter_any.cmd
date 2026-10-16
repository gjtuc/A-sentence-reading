@echo off
rem design/403 - bypass execution policy; run flutter with args in mobile\.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0flutter_any.ps1" %*
exit /b %ERRORLEVEL%
