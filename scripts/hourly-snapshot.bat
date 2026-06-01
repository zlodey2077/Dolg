@echo off
REM ========================================================================
REM DOLG hourly-snapshot — резервная копия проекта раз в час
REM
REM 2026-06-01: дополнительная защита между git push'ами.
REM Сохраняет tar.gz в OneDrive (или указанную папку), keep last 24.
REM
REM Настройка Task Scheduler:
REM   schtasks /create /sc hourly /tn "DOLG hourly backup" ^
REM            /tr "C:\Users\spieh\Desktop\DOLG_Diploma\scripts\hourly-snapshot.bat" ^
REM            /st 00:00
REM
REM Проверка очереди:
REM   schtasks /query /tn "DOLG hourly backup"
REM
REM Удалить:
REM   schtasks /delete /tn "DOLG hourly backup" /f
REM ========================================================================

setlocal enabledelayedexpansion

REM Папка с проектом (откуда запускается скрипт — поднимаемся на уровень вверх)
set "PROJECT=%~dp0.."
pushd "%PROJECT%"

REM Папка-приёмник: OneDrive / OneDrive Personal / fallback на локальную backups/
set "DEST=%USERPROFILE%\OneDrive\DOLG-backups"
if not exist "%DEST%" set "DEST=%USERPROFILE%\OneDrive - Personal\DOLG-backups"
if not exist "%DEST%" set "DEST=%PROJECT%\backups"
if not exist "%DEST%" mkdir "%DEST%"

REM Имя архива: dolg-2026-06-01_14-00.tar.gz
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "TS=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%_%dt:~8,2%-%dt:~10,2%"
set "ARCHIVE=%DEST%\dolg-%TS%.tar.gz"

echo [%date% %time%] DOLG snapshot -^> %ARCHIVE%

REM Архив. Исключаем тяжёлое (venv, media, кэши, node_modules).
tar -czf "%ARCHIVE%" ^
    --exclude=.venv ^
    --exclude=.git ^
    --exclude=__pycache__ ^
    --exclude=node_modules ^
    --exclude=.pytest_cache ^
    --exclude=.ruff_cache ^
    --exclude=.mypy_cache ^
    --exclude=staticfiles ^
    --exclude=media/products ^
    --exclude=media/avatars ^
    --exclude=media/ml ^
    --exclude=Dolg_APP/ml/dataset/external ^
    --exclude=Dolg_APP/ml/dataset/hf_cache ^
    --exclude=backups ^
    --exclude=deploy/cloudflared.exe ^
    --exclude=db.sqlite3 ^
    --exclude=*.recovery-* ^
    .

if errorlevel 1 (
    echo [ERROR] tar failed
    popd
    exit /b 1
)

REM Cleanup: оставляем последние 24 (т.е. сутки часовых снапшотов).
REM forfiles удаляет файлы старше 24 часов по mtime.
forfiles /p "%DEST%" /m "dolg-*.tar.gz" /d -1 /c "cmd /c del @path" 2>nul

echo [OK] backup сохранён.
popd
exit /b 0
