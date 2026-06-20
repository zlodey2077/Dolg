@echo off
setlocal
set "SCRIPT=%~dp0apply_system_performance_fixes_admin.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoExit -NoProfile -ExecutionPolicy Bypass -File ""%SCRIPT%""'"
