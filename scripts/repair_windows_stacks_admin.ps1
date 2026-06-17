param(
    [switch]$EnableFullHyperV,
    [switch]$StartDockerDesktop
)

$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir ("windows-stack-repair-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

Start-Transcript -Path $logPath -Append | Out-Null

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Enable-Feature {
    param([string]$Name)
    Write-Host "Enabling optional feature: $Name"
    try {
        $result = Enable-WindowsOptionalFeature -Online -FeatureName $Name -All -NoRestart -ErrorAction Stop
        if ($result.RestartNeeded) {
            $script:RestartRequired = $true
        }
    } catch {
        Write-Warning "Could not enable ${Name}: $($_.Exception.Message)"
    }
}

function Start-ServiceSafe {
    param([string]$Name)
    try {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status -ne "Running") {
            Start-Service -Name $Name -ErrorAction Stop
            $service.Refresh()
        }
        Write-Host "${Name}: $($service.Status)"
    } catch {
        Write-Warning "Could not start ${Name}: $($_.Exception.Message)"
    }
}

function Set-ServiceStartupTimeout {
    $path = "HKLM:\SYSTEM\CurrentControlSet\Control"
    $name = "ServicesPipeTimeout"
    $value = 180000
    try {
        New-ItemProperty -Path $path -Name $name -Value $value -PropertyType DWord -Force | Out-Null
        Write-Host "${name}: $value ms"
        $script:RestartRequired = $true
    } catch {
        Write-Warning "Could not set ${name}: $($_.Exception.Message)"
    }
}

if (-not (Test-IsAdmin)) {
    Write-Error "Run this script from an elevated PowerShell session."
    Stop-Transcript | Out-Null
    exit 1
}

$script:RestartRequired = $false

Write-Host "DOLG Windows stack repair"
Write-Host "Root: $root"
Write-Host "Log: $logPath"
Write-Host "This script does not install Linux distributions."

Write-Step "Stop stuck Docker and WSL processes"
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

Write-Step "Extend Windows service startup timeout"
Set-ServiceStartupTimeout

Write-Step "Enable required Windows features"
Enable-Feature "Microsoft-Windows-Subsystem-Linux"
Enable-Feature "VirtualMachinePlatform"
Enable-Feature "HypervisorPlatform"
if ($EnableFullHyperV) {
    Enable-Feature "Microsoft-Hyper-V-All"
} else {
    Write-Host "Skipping Microsoft-Hyper-V-All. Pass -EnableFullHyperV if Docker still cannot start on this Windows edition."
}

Write-Step "Enable hypervisor boot"
try {
    bcdedit /set hypervisorlaunchtype auto
} catch {
    Write-Warning "Could not set hypervisorlaunchtype: $($_.Exception.Message)"
}

Write-Step "Refresh WSL"
try {
    wsl --update
    wsl --set-default-version 2
} catch {
    Write-Warning "Could not refresh WSL: $($_.Exception.Message)"
}

Write-Step "Start services"
Start-ServiceSafe "vmcompute"
Start-ServiceSafe "LxssManager"
Start-ServiceSafe "com.docker.service"

Write-Step "Current WSL state"
wsl --status
wsl -l -v

if ($RestartRequired) {
    Write-Host ""
    Write-Host "Restart is required before Docker Desktop can be tested reliably."
} elseif ($StartDockerDesktop) {
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
        Write-Step "Start Docker Desktop"
        Start-Process -FilePath $dockerDesktop
    } else {
        Write-Warning "Docker Desktop executable was not found at $dockerDesktop"
    }
}

Write-Host ""
Write-Host "Done. Rerun scripts\check_vscode_stacks.ps1 after restart or after Docker Desktop reaches Running state."
Stop-Transcript | Out-Null
