$ErrorActionPreference = "Continue"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Error "Run this script from an elevated PowerShell session."
    exit 1
}

Write-Host "Stopping Docker Desktop, Docker backend, and stuck Docker CLI processes..."
wsl --shutdown 2>$null

$processNames = @(
    "docker",
    "Docker Desktop",
    "com.docker.backend",
    "com.docker.build",
    "com.docker.proxy",
    "com.docker.service",
    "docker-sandbox",
    "vpnkit"
)

foreach ($name in $processNames) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

try {
    Stop-Service -Name "com.docker.service" -Force -ErrorAction SilentlyContinue
} catch {
}

Start-Sleep -Seconds 3
Get-Process -Name $processNames -ErrorAction SilentlyContinue |
    Select-Object ProcessName, Id, StartTime

Write-Host "Done."
