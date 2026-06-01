@echo off
REM ============================================================
REM DOLG — local dev launcher (127.0.0.1:8000)
REM    Starts Django runserver in its own window and opens the
REM    browser when the server is ready. Use this for solo work.
REM    For public access (phone / external review) use
REM    start_public.bat — it adds Cloudflare Quick Tunnel.
REM ============================================================
setlocal
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8000"
set "URL=http://%HOST%:%PORT%/"

REM --- Python detection ---
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python is not found ^(neither .venv nor system PATH^).
        echo         Install Python 3.11+ and run:  python -m venv .venv
        pause
        exit /b 1
    )
    set "PY=python"
)

REM --- Port already busy? Probe before launching a second server. ---
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=New-Object Net.Sockets.TcpClient; try { $c.Connect('%HOST%',%PORT%); $c.Close(); exit 0 } catch { exit 1 }"
if %errorlevel% equ 0 (
    echo Port %PORT% is already in use — assuming DOLG is already running.
    echo Opening browser at %URL%
    start "" "%URL%"
    timeout /t 2 /nobreak >nul
    exit /b 0
)

echo Starting DOLG dev server on %URL% ...
REM --skip-checks: пропускаем системные проверки Django (экономит 1-2 сек на старте,
REM безопасно для dev — ошибки конфига всё равно вылезут при первом запросе).
start "DOLG Django Server" /min cmd /k "cd /d ""%~dp0"" && set ""DEBUG=True"" && ""%PY%"" manage.py runserver %HOST%:%PORT% --skip-checks"

echo Waiting for server to respond ^(max 90 sec^) ...
REM 90 сек: daphne (ASGI/WebSocket) + миграции на холодную SQLite берут до 60+
REM на слабых машинах. Раньше было 45 — упирались в timeout.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(90); do { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%URL%'; if ($r.StatusCode -lt 500) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo.
    echo [ERROR] Server did not respond. Check the "DOLG Django Server" window for traceback.
    pause
    exit /b 1
)

start "" "%URL%"
echo.
echo DOLG is open: %URL%
echo Close the "DOLG Django Server" window to stop.
timeout /t 3 /nobreak >nul
exit /b 0
