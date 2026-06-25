@echo off
REM ============================================================
REM DOLG - public launcher (Django + Cloudflare Quick Tunnel)
REM    Delegates to start_public_server.py, which:
REM      1) starts Django on 127.0.0.1:8000 through the local launcher
REM      2) starts deploy\cloudflared.exe Quick Tunnel
REM      3) waits for the public URL, then opens the browser
REM    Use this for sharing with reviewers / phone testing.
REM    For solo work on the same machine - use start_local.bat.
REM
REM    ngrok is NOT used by default because free ngrok domains show a warning page.
REM ============================================================
title DOLG public launcher
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

if not exist "deploy\cloudflared.exe" (
    echo [ERROR] deploy\cloudflared.exe not found.
    echo         Public ngrok mode is disabled by default to avoid its browser warning page.
    pause
    exit /b 1
)
if not exist "start_public_server.py" (
    echo [ERROR] start_public_server.py not found. Repo is incomplete.
    pause
    exit /b 1
)

echo Starting DOLG public launcher ^(Cloudflare Quick Tunnel^) via %PY% ...
echo.

"%PY%" start_public_server.py

echo.
echo === Launcher finished. This window stays open so you can see errors. ===
pause
