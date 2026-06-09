@echo off
REM ============================================================
REM DOLG - local dev launcher (127.0.0.1:8000)
REM    Delegates to start_server.py --local, which:
REM      1) frees the port if a stale python server is holding it
REM         (guarantees you always test the CURRENT code, not a zombie)
REM      2) starts Django in stable plain mode with autoreload disabled.
REM         Hot/jurigged is useful for experiments, but on Windows terminals it can
REM         emit control-sequence probes and fail before Django is ready.
REM      3) logs server output to .tmp_django.log (survives window close)
REM      4) opens the browser when the server is ready
REM    No Cloudflare tunnel. For public / phone testing use start_public.bat.
REM    To try hot-reload manually, run:
REM       .venv\Scripts\python.exe start_server.py --local --hot
REM ============================================================
title DOLG local launcher
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

if not exist "manage.py" (
    echo [ERROR] manage.py not found - wrong folder or incomplete repo.
    pause
    exit /b 1
)
if not exist "start_server.py" (
    echo [ERROR] start_server.py not found - repo is incomplete.
    pause
    exit /b 1
)

echo Starting DOLG local server via %PY% ...
echo.

"%PY%" start_server.py --local --no-hot

echo.
echo === Launcher finished. This window stays open so you can see errors. ===
pause
