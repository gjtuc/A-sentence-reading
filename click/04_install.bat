@echo off
rem Install the last built APK on the one connected phone (no deploy). Result: click\out\install.result.txt
call "%~dp0_job.cmd" install
