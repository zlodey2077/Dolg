@echo off
REM ============================================================
REM DOLG - local dev launcher (127.0.0.1:8000)
REM    Delegates to start_server.py --local, which:
REM      1) frees the port if a stale python server is holding it
REM         (guarantees you always test the CURRENT code, not a zombie)
REM      2) starts Django with HOT-reload via jurigged: edits to function
REM         bodies apply in the LIVE process in <1s, no restart. Structural
REM         edits (new URL / model / settings) still need a restart of this window.
REM      3) logs server output to .tmp_django.log (survives window close)
REM      4) opens the browser when the server is ready
REM    No Cloudflare tunnel. For public / phone testing use start_public.bat.
REM    To disable hot-reload (plain runserver) replace --hot with --no-hot below.
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

"%PY%" start_server.py --local --hot

echo.
echo === Launcher finished. This window stays open so you can see errors. ===
pause
