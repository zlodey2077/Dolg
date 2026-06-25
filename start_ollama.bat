@echo off
title DOLG Ollama local AI
cd /d "%~dp0"

set "OLLAMA_EXE=ollama"
where ollama >nul 2>nul
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"

if "%OLLAMA_MODEL%"=="" set "OLLAMA_MODEL=qwen3:0.6b"

echo Starting Ollama for DOLG local AI...
echo Model: %OLLAMA_MODEL%

start "DOLG Ollama Serve" /min "%OLLAMA_EXE%" serve
timeout /t 3 /nobreak >nul

echo Pulling/checking model %OLLAMA_MODEL% ...
"%OLLAMA_EXE%" pull %OLLAMA_MODEL%

echo.
echo Ollama is ready on http://127.0.0.1:11434
echo Use in Django env: OLLAMA_BASE_URL=http://127.0.0.1:11434
pause
