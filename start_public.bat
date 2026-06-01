@echo off
REM ============================================================
REM DOLG — public launcher (Django + Cloudflare Quick Tunnel)
REM    Hands off to start_server.py which:
REM      1) starts Django on 127.0.0.1:8000
REM      2) starts cloudflared and waits for trycloudflare.com URL
REM      3) probes the URL until propagated, then opens browser
REM    Use this for sharing with reviewers / phone testing.
REM    For solo work on the same machine — use start_local.bat.
REM
REM    Auto-reload AKTIVEN: Django sledit za .py / urls.py / *.html i
REM    perezapuskaet rebenok-process pri save. Cloudflared tunnel pereletivayet
REM    avtomaticheski (1-2 sek pasa porta). Perezapusk start_public.bat
REM    nuzhen tolko esli upal sam parent-process (kraine redko).
REM ============================================================
title DOLG public launcher
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

REM cloudflared.exe лежит в deploy/ — там же, где Docker-инфра.
if not exist "deploy\cloudflared.exe" if not exist "cloudflared.exe" (
    echo [ERROR] cloudflared.exe not found in deploy\ or project folder.
    echo         Download Windows build: https://github.com/cloudflare/cloudflared/releases
    pause
    exit /b 1
)
if not exist "start_server.py" (
    echo [ERROR] start_server.py not found. Repo is incomplete.
    pause
    exit /b 1
)

echo Starting DOLG public launcher via %PY% ...
echo.

"%PY%" start_server.py

echo.
echo === Launcher finished. This window stays open so you can see errors. ===
pause
