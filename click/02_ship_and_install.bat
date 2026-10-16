@echo off
rem Guards, ship, live verify, APK build, phone install. Stops at the first failure.
rem Result: click\out\ship_install.result.txt
call "%~dp0_job.cmd" ship_install
