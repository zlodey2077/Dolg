@echo off
REM ============================================================
REM DOLG - public launcher (Django + ngrok tunnel)
REM    Delegates to start_server.py (no --local), which:
REM      1) frees the port, starts Django on 127.0.0.1:8000 (stable mode)
REM      2) starts ngrok and waits for the https://...ngrok-free.dev URL
REM      3) probes the URL, then opens the browser
REM    Use this for sharing with reviewers / phone testing.
REM    For solo work on the same machine - use start_local.bat.
REM
REM    One-time setup: ngrok config add-authtoken YOUR_TOKEN  (token at ngrok.com).
REM    ngrok.exe is bundled in deploy\. Cloudflare dropped (kept giving error 1033).
REM ============================================================
title DOLG public launcher
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

where ngrok >nul 2>nul
if not exist "deploy\ngrok.exe" if not exist "ngrok.exe" if errorlevel 1 (
    echo [ERROR] ngrok.exe not found in deploy\, project folder, or PATH.
    echo         Install: winget install --id Ngrok.Ngrok --exact
    echo         Then:    ngrok config add-authtoken YOUR_TOKEN
    pause
    exit /b 1
)
if not exist "start_server.py" (
    echo [ERROR] start_server.py not found. Repo is incomplete.
    pause
    exit /b 1
)

echo Starting DOLG public launcher ^(ngrok^) via %PY% ...
echo.

"%PY%" start_server.py

echo.
echo === Launcher finished. This window stays open so you can see errors. ===
pause
