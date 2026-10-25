@echo off
rem design/451 - USB sync helper. The desktop app shortcut starts it by itself.
rem Use this only without the shortcut. Keep the window open while syncing.
python "%~dp0usb_sync_bridge.py"
pause
