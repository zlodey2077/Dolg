@echo off
setlocal
set "SCRIPT=%~dp0prepare_lxss_docker_k8s_admin.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoExit -NoProfile -ExecutionPolicy Bypass -File ""%SCRIPT%""'"
