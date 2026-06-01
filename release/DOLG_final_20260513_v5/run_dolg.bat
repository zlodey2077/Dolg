@echo off
setlocal

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8000"
set "URL=http://127.0.0.1:8000/"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo Starting DOLG...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$client = New-Object Net.Sockets.TcpClient; try { $client.Connect('%HOST%', %PORT%); $client.Close(); exit 0 } catch { exit 1 }"
if errorlevel 1 (
    start "DOLG Django Server" /min cmd /k "cd /d ""%~dp0"" && set ""DEBUG=True"" && ""%PY%"" manage.py runserver %HOST%:%PORT%"
)

echo Waiting for http://%HOST%:%PORT%/ ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(45); do { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%URL%'; if ($r.StatusCode -lt 500) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo.
    echo [ERROR] DOLG did not start. Check the "DOLG Django Server" window.
    pause
    exit /b 1
)

start "" "%URL%"
echo.
echo DOLG is open: %URL%
echo Close the "DOLG Django Server" window to stop the site.
timeout /t 3 /nobreak >nul
exit /b 0
