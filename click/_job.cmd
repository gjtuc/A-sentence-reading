@echo off
rem design/402 - ASR click runner: _job.cmd JOB
rem Opens its own window that stays open. Output: click\out\JOB.log and JOB.result.txt
if /i not "%~1"=="run" (
  start "ASR - %~1" cmd /k ""%~f0" run %1"
  exit /b
)
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python -u click\_run.py %~2
