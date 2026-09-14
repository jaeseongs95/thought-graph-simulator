@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-v079.ps1"
exit /b %errorlevel%
