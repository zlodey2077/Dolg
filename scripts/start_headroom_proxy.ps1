# Starts the Headroom optimization proxy on :8787 if it isn't already running.
# Idempotent: a healthy proxy is left alone, so this is safe to run at every
# logon and from setup_mcp.mjs. The Headroom MCP server (headroom_compress /
# _retrieve / _stats, wired into Claude Code) talks to this proxy, so the proxy
# must be up before Claude Code starts a session -- otherwise `mcp serve` blocks
# on it and hits Claude Code's 30s connection timeout.
#
# Usage:
#   scripts\start_headroom_proxy.ps1              # ensure proxy is running
#   scripts\start_headroom_proxy.ps1 -InstallTask # also register a logon task
#   scripts\start_headroom_proxy.ps1 -Stop        # stop the proxy
#
# Rust core is intentionally not required (HEADROOM_REQUIRE_RUST_CORE=false):
# the wheel ships without the native module, so the proxy runs in Python mode.

param(
  [int]$Port = 8787,
  [switch]$InstallTask,
  [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $repo '.venv\Scripts\python.exe'
$logDir = Join-Path $repo 'logs'
$taskName = 'HeadroomProxy'

function Test-ProxyHealthy {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/livez" -TimeoutSec 3
    return ($r.alive -eq $true)
  } catch { return $false }
}

if ($Stop) {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'headroom' -and $_.CommandLine -match 'proxy' } |
    ForEach-Object { Write-Host "Stopping proxy PID $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force }
  return
}

if ($InstallTask) {
  # Use the per-user Startup folder rather than a scheduled task: it needs no
  # elevation (schtasks /Create ONLOGON is denied without admin on this box).
  $self = $MyInvocation.MyCommand.Path
  $startup = [Environment]::GetFolderPath('Startup')
  $cmd = Join-Path $startup "$taskName.cmd"
  $body = "@echo off`r`npowershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$self`" -Port $Port`r`n"
  Set-Content -Path $cmd -Value $body -Encoding ASCII
  Write-Host "Installed startup launcher: $cmd"
  Write-Host "Proxy will start automatically at next sign-in (no reboot needed now; it is started below)."
}

if (Test-ProxyHealthy) {
  Write-Host "Headroom proxy already healthy on :$Port."
  return
}

if (-not (Test-Path $python)) { throw "venv python not found at $python - create .venv and pip install headroom-ai first." }
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$env:HEADROOM_REQUIRE_RUST_CORE = 'false'
Start-Process -FilePath $python `
  -ArgumentList '-c', 'from headroom.cli import main; main()', 'proxy', '--port', $Port, '--no-telemetry' `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $logDir 'headroom_proxy.out.log') `
  -RedirectStandardError  (Join-Path $logDir 'headroom_proxy.err.log') | Out-Null

Write-Host "Starting Headroom proxy on :$Port ..."
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  if (Test-ProxyHealthy) { Write-Host "Proxy ready after $($i + 1)s."; return }
}
throw "Proxy did not become healthy within 30s -- check logs\headroom_proxy.err.log"
