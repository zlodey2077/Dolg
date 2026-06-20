param(
    [string]$OutputDir = "logs",
    [switch]$SkipHappService,
    [switch]$SkipTunnelNetbios,
    [switch]$SkipDpsRestart
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "== $Message =="
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Error "This script must be run as Administrator."
    exit 1
}

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resolvedLogDir = (Resolve-Path -LiteralPath $OutputDir).Path

Write-Step "Backups"
$runBackup = Join-Path $resolvedLogDir "hkcu-run-before-system-performance-fixes-$stamp.reg"
$happBackup = Join-Path $resolvedLogDir "happservice-before-system-performance-fixes-$stamp.reg"
$netbtBackup = Join-Path $resolvedLogDir "netbt-interfaces-before-system-performance-fixes-$stamp.reg"

reg export "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" $runBackup /y | Out-Host
reg export "HKLM\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces" $netbtBackup /y | Out-Host

if (Test-Path -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\HappService") {
    reg export "HKLM\SYSTEM\CurrentControlSet\Services\HappService" $happBackup /y | Out-Host
}

Write-Step "Startup cleanup"
$runPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$startupValues = @(
    "Docker Desktop",
    "Opera GX Stable",
    "YandexBrowserAutoLaunch_2FCAB3CEC07D188D1F5CDF88222B8050"
)

foreach ($valueName in $startupValues) {
    try {
        $current = Get-ItemProperty -LiteralPath $runPath -Name $valueName -ErrorAction Stop
        if ($null -ne $current) {
            Remove-ItemProperty -LiteralPath $runPath -Name $valueName -ErrorAction Stop
            Write-Host "Removed startup value: $valueName"
        }
    }
    catch {
        Write-Host "Startup value not present: $valueName"
    }
}

if (-not $SkipHappService) {
    Write-Step "Happ Proxy Client Service"
    $service = Get-Service -Name HappService -ErrorAction SilentlyContinue
    if ($service) {
        if ($service.Status -ne "Stopped") {
            Stop-Service -Name HappService -Force -ErrorAction SilentlyContinue
        }
        sc.exe config HappService start= disabled | Out-Host
        sc.exe queryex HappService | Out-Host
    }
    else {
        Write-Host "HappService is not installed."
    }
}

if (-not $SkipTunnelNetbios) {
    Write-Step "Disable NetBIOS on tunnel adapters"
    $tunnelAdapters = @(Get-CimInstance Win32_NetworkAdapterConfiguration |
        Where-Object {
            $_.Description -match "Xray|Wintun|TAP-Windows|WireGuard|OpenVPN|Outline"
        })

    if (-not $tunnelAdapters) {
        Write-Host "No tunnel adapters found."
    }

    foreach ($adapter in $tunnelAdapters) {
        $keyName = "Tcpip_$($adapter.SettingID.ToLowerInvariant())"
        $keyPath = "HKLM:\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\Interfaces\$keyName"
        if (Test-Path -LiteralPath $keyPath) {
            Set-ItemProperty -LiteralPath $keyPath -Name NetbiosOptions -Type DWord -Value 2
            Write-Host "NetBIOS disabled for #$($adapter.Index): $($adapter.Description)"
        }
        else {
            Write-Warning "NetBT key not found for #$($adapter.Index): $($adapter.Description)"
        }
    }
}

if (-not $SkipDpsRestart) {
    Write-Step "Diagnostic Policy Service"
    try {
        Restart-Service -Name DPS -Force -ErrorAction Stop
        Start-Sleep -Seconds 3
        $dps = Get-Service -Name DPS -ErrorAction Stop
        if ($dps.Status -eq "StopPending") {
            throw "DPS is still StopPending after restart request."
        }
        Write-Host "DPS status: $($dps.Status)"
    }
    catch {
        Write-Warning "Could not restart DPS cleanly: $($_.Exception.Message)"
        $dpsService = Get-CimInstance Win32_Service -Filter "Name='DPS'" -ErrorAction SilentlyContinue
        if ($dpsService -and $dpsService.State -eq "Stop Pending" -and $dpsService.ProcessId -gt 0) {
            Write-Warning "DPS is stuck in StopPending. Forcing only its service host process #$($dpsService.ProcessId)."
            tasklist.exe /svc /FI "PID eq $($dpsService.ProcessId)" | Out-Host
            taskkill.exe /PID $dpsService.ProcessId /F | Out-Host
            Start-Sleep -Seconds 3
            Start-Service -Name DPS -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            Get-Service -Name DPS -ErrorAction SilentlyContinue | Format-Table -AutoSize | Out-Host
        }
    }
}

Write-Step "DNS cache"
ipconfig /flushdns | Out-Host

Write-Step "Done"
Write-Host "Backups written to: $resolvedLogDir"
Write-Host "Reboot is recommended before re-checking NetBT/DPS and Docker virtualization status."
