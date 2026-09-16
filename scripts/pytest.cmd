@echo off
rem design/303 - bypass execution policy. Pin cwd and PYTHONPATH to this repo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pytest.ps1" %*
exit /b %ERRORLEVEL%
