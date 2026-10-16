@echo off
rem Install the APK on the one connected phone; builds it first when it is not the app version.
rem No deploy. Result: click\out\install.result.txt
call "%~dp0_job.cmd" install
