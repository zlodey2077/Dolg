# Install server SPICE engines (ngspice CLI) - RUN AS ADMINISTRATOR.
#
# PySpice + the ngspice DLL are already installed in .venv (working engine). This script
# installs the standalone ngspice CLI via choco (needs admin: both the install and clearing
# a stale lock left by an earlier crashed/parallel choco). Xyce and GnuCap have no package
# manager - install them manually (links at the end).
#
# Run: right-click -> "Run with PowerShell" as admin, or from an elevated console:
#   powershell -ExecutionPolicy Bypass -File scripts\install_server_engines_admin.ps1
#
# ASCII-only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI without a BOM, so any
# non-ASCII text would be mangled and break parsing.
#Requires -RunAsAdministrator

$ErrorActionPreference = 'Continue'

Write-Host '== Server SPICE engines ==' -ForegroundColor Cyan

# 1) Clear choco stale locks (left by a crashed/parallel process), else install fails with
#    "Unable to obtain lock file access".
$lockDir = 'C:\ProgramData\chocolatey\lib'
if (Test-Path $lockDir) {
    Get-ChildItem $lockDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^[0-9a-f]{40}$' } |
        ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue; Write-Host "  removed lock $($_.Name)" }
    Remove-Item (Join-Path $lockDir 'ngspice') -Recurse -Force -ErrorAction SilentlyContinue
}

# 2) ngspice CLI
Write-Host '-- choco install ngspice --' -ForegroundColor Cyan
choco install ngspice -y --force

# 3) Verify
$ng = Get-Command ngspice -ErrorAction SilentlyContinue
if ($ng) {
    Write-Host "ngspice CLI: $($ng.Source)" -ForegroundColor Green
}
else {
    Write-Host 'ngspice CLI not on PATH - reopen the console or check the choco log' -ForegroundColor Yellow
}

# 4) Xyce / GnuCap - native, manual install (not in package managers)
Write-Host ''
Write-Host '== Manual install (not in package managers) ==' -ForegroundColor Cyan
Write-Host '  Xyce:   https://xyce.sandia.gov/downloads/  (free registration, Windows installer, add to PATH)'
Write-Host '  GnuCap: http://www.gnucap.org/  (binary or build, add to PATH)'
Write-Host ''
Write-Host 'Done. PySpice + ngspice DLL already work in .venv regardless of this step.' -ForegroundColor Green
