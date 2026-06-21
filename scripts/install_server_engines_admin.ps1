# Установка серверных SPICE-движков (ngspice CLI) — ЗАПУСКАТЬ ОТ ИМЕНИ АДМИНИСТРАТОРА.
#
# PySpice + ngspice DLL уже стоят в .venv (рабочий движок). Этот скрипт ставит standalone
# ngspice CLI через choco (нужен admin: и сам install, и снятие stale-lock от упавшего ранее
# choco). Xyce и GnuCap — нативные без пакет-менеджера, ставятся вручную (ссылки в конце).
#
# Запуск: правый клик → «Запустить с помощью PowerShell» от админа, или из elevated-консоли:
#   powershell -ExecutionPolicy Bypass -File scripts\install_server_engines_admin.ps1
#Requires -RunAsAdministrator

$ErrorActionPreference = 'Continue'

Write-Host '== Серверные SPICE-движки ==' -ForegroundColor Cyan

# 1) Снять stale-lock'и choco (остались от упавшего/параллельного процесса), иначе install
#    падает «Unable to obtain lock file access».
$lockDir = 'C:\ProgramData\chocolatey\lib'
if (Test-Path $lockDir) {
    Get-ChildItem $lockDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^[0-9a-f]{40}$' } |
        ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue; Write-Host "  снят lock $($_.Name)" }
    Remove-Item (Join-Path $lockDir 'ngspice') -Recurse -Force -ErrorAction SilentlyContinue
}

# 2) ngspice CLI
Write-Host '-- choco install ngspice --' -ForegroundColor Cyan
choco install ngspice -y --force

# 3) Проверка
$ng = Get-Command ngspice -ErrorAction SilentlyContinue
if ($ng) { Write-Host "ngspice CLI: $($ng.Source)" -ForegroundColor Green }
else { Write-Host 'ngspice CLI не в PATH — перезапустите консоль или проверьте choco-лог' -ForegroundColor Yellow }

# 4) Xyce / GnuCap — нативные, ручная загрузка (нет в choco/winget)
Write-Host ''
Write-Host '== Ручная установка (нет в пакет-менеджерах) ==' -ForegroundColor Cyan
Write-Host '  Xyce:   https://xyce.sandia.gov/downloads/  (бесплатная регистрация, Windows installer, в PATH)'
Write-Host '  GnuCap: http://www.gnucap.org/  (бинарь/сборка, в PATH)'
Write-Host ''
Write-Host 'Готово. PySpice+ngspice DLL уже работают в .venv независимо от этого шага.' -ForegroundColor Green
