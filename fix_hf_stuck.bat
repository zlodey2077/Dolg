@echo off
REM ============================================================
REM  fix_hf_stuck.bat - free up stuck HF import
REM
REM  English-only because Windows cmd hates Russian in .bat
REM  (codepage 866 vs 1251 vs UTF-8 = endless pain).
REM
REM  Double-click and follow prompts.
REM ============================================================
title DOLG: free HF import

echo.
echo === STEP 1: Search for python.exe processes ===
echo.
tasklist /FI "IMAGENAME eq python.exe" /FO TABLE
echo.
echo If you see python.exe above - those are Django server and import thread.
echo They need to be stopped so the .incomplete file gets released.
echo.

choice /C YN /M "Kill ALL python.exe processes"
if errorlevel 2 goto skip_kill

echo.
echo === Stopping python.exe ... ===
taskkill /F /IM python.exe /T 2>nul
if errorlevel 1 (
    echo No python.exe was running.
) else (
    echo Done.
)
timeout /t 2 /nobreak >nul

:skip_kill

echo.
echo === STEP 2: Delete broken .incomplete files ===
echo.
set "HF_CACHE=%USERPROFILE%\.cache\huggingface\hub\datasets--bshada--open-schematics\blobs"
if not exist "%HF_CACHE%" (
    echo Folder %HF_CACHE% not found.
    echo HF cache is empty - nothing to delete.
    goto end_ok
)

dir /b "%HF_CACHE%\*.incomplete" 2>nul
echo.
choice /C YN /M "Delete all .incomplete files"
if errorlevel 2 goto skip_delete

del /F /Q "%HF_CACHE%\*.incomplete" 2>nul
if errorlevel 1 (
    echo [ERROR] Could not delete - file still locked.
    echo Try:
    echo   1. Reboot Windows
    echo   2. Or delete manually via Explorer:
    echo      %HF_CACHE%
) else (
    echo Done, files deleted.
)

:skip_delete

echo.
echo === STEP 3: Verify ===
echo.
dir /b "%HF_CACHE%\*.incomplete" 2>nul
if errorlevel 1 (
    echo Clean - no .incomplete files left.
    echo Now run start_local.bat and press "Start import" in the UI.
) else (
    echo Broken files still here. Reboot Windows and run this .bat again.
)

:end_ok
echo.
echo === Done ===
pause
