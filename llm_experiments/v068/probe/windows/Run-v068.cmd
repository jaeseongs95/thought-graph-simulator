@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-v068.ps1"
exit /b %errorlevel%
