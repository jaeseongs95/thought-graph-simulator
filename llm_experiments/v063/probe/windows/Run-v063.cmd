@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-v063.ps1" %*
exit /b %ERRORLEVEL%
