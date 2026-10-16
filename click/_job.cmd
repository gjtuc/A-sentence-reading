@echo off
rem design/402 - ASR click runner: _job.cmd JOB
rem Opens its own window that stays open. Output: click\out\JOB.log and JOB.result.txt
rem design/406 - when the job's Python dies before writing DONE or FAILED (no memory),
rem wait 15 s and run the job again from the top. _run.py removes JOB.restart_ok
rem once that is no longer safe (the deploy step started) and when the job ends.
if /i not "%~1"=="run" (
  start "ASR - %~1" cmd /k ""%~f0" run %1"
  exit /b
)
cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set ASR_CLICK_TRY=0
:again
python -u click\_run.py %~2
set RC=%errorlevel%
if "%RC%"=="2" goto :eof
if "%RC%"=="3" goto :eof
findstr /b /c:"DONE" /c:"FAILED" "click\out\%~2.result.txt" >nul 2>&1 && goto :eof
if not exist "click\out\%~2.restart_ok" goto :eof
set /a ASR_CLICK_TRY+=1
if %ASR_CLICK_TRY% GTR 20 goto :eof
ping -n 16 127.0.0.1 >nul
goto again
