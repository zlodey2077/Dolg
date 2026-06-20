param(
    [string]$OutputDir = "logs"
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outFile = Join-Path $OutputDir "windows-driver-audit-$stamp.md"
$lines = [System.Collections.Generic.List[string]]::new()

function Add-Line([string]$Text = "") {
    [void]$lines.Add($Text)
}

function Add-Table($Rows) {
    $text = ($Rows | Out-String -Width 280).TrimEnd()
    if ([string]::IsNullOrWhiteSpace($text)) {
        Add-Line "_no data_"
    }
    else {
        Add-Line '```text'
        Add-Line $text
        Add-Line '```'
    }
}

function Convert-CimDate([string]$Value) {
    if (-not $Value) { return "" }
    try {
        return ([System.Management.ManagementDateTimeConverter]::ToDateTime($Value)).ToString("yyyy-MM-dd")
    }
    catch {
        return $Value
    }
}

Add-Line "# Windows Driver Audit"
Add-Line ""
Add-Line "- Time: $(Get-Date -Format s)"
Add-Line "- Repo: $RepoRoot"
Add-Line "- Note: serial numbers are intentionally omitted."
Add-Line ""

Add-Line "## System And BIOS"
Add-Line ""
try {
    $computer = Get-CimInstance Win32_ComputerSystem |
        Select-Object Manufacturer, Model, SystemType,
            @{Name = "RAM_GB"; Expression = { [math]::Round($_.TotalPhysicalMemory / 1GB, 1) } },
            HypervisorPresent
    $bios = Get-CimInstance Win32_BIOS |
        Select-Object Manufacturer, SMBIOSBIOSVersion,
            @{Name = "ReleaseDate"; Expression = { Convert-CimDate $_.ReleaseDate } }
    $os = Get-CimInstance Win32_OperatingSystem |
        Select-Object Caption, Version, BuildNumber, OSArchitecture
    Add-Table @($computer, $bios, $os)
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Virtualization"
Add-Line ""
try {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    Add-Table ([pscustomobject]@{
        Name = $cpu.Name
        VMMonitorModeExtensions = $cpu.VMMonitorModeExtensions
        SecondLevelAddressTranslationExtensions = $cpu.SecondLevelAddressTranslationExtensions
        VirtualizationFirmwareEnabled = $cpu.VirtualizationFirmwareEnabled
    })
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Problem Devices"
Add-Line ""
try {
    Add-Table (Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.Status -ne "OK" -or $_.ConfigManagerErrorCode -ne 0 } |
        Select-Object Name, PNPClass, Status, ConfigManagerErrorCode, DeviceID |
        Sort-Object PNPClass, Name)
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Key Signed Drivers"
Add-Line ""
try {
    $driverClasses = @("DISPLAY", "NET", "BLUETOOTH", "HDC", "SCSIADAPTER", "SYSTEM", "MEDIA", "USB")
    $providerPattern = "AMD|Advanced Micro Devices|Realtek|Qualcomm|Atheros|Microsoft|KB9X|Docker|Wintun|TAP"
    Add-Table (Get-CimInstance Win32_PnPSignedDriver |
        Where-Object {
            $driverClasses -contains ([string]$_.DeviceClass).ToUpperInvariant() -and
            ($_.DriverProviderName -match $providerPattern -or $_.DeviceName -match $providerPattern)
        } |
        Select-Object DeviceClass, DeviceName, DriverProviderName, DriverVersion,
            @{Name = "DriverDate"; Expression = { Convert-CimDate $_.DriverDate } },
            InfName |
        Sort-Object DeviceClass, DeviceName)
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Disks And Volumes"
Add-Line ""
try {
    $disks = Get-CimInstance Win32_DiskDrive |
        Select-Object Model, InterfaceType, MediaType, Status,
            @{Name = "SizeGB"; Expression = { [math]::Round($_.Size / 1GB, 1) } }
    $volumes = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
        Select-Object DeviceID, FileSystem,
            @{Name = "SizeGB"; Expression = { [math]::Round($_.Size / 1GB, 1) } },
            @{Name = "FreeGB"; Expression = { [math]::Round($_.FreeSpace / 1GB, 1) } },
            @{Name = "FreePct"; Expression = { if ($_.Size) { [math]::Round($_.FreeSpace / $_.Size * 100, 1) } else { 0 } } }
    Add-Table @($disks + $volumes)
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Network Adapters"
Add-Line ""
try {
    Add-Table (Get-NetAdapter -IncludeHidden |
        Select-Object Name, InterfaceDescription, Status, LinkSpeed, ifIndex |
        Sort-Object Status, Name)
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Relevant Services"
Add-Line ""
try {
    $names = @("HappService", "DPS", "LxssManager", "vmcompute", "hns", "com.docker.service")
    Add-Table (Get-CimInstance Win32_Service |
        Where-Object { $names -contains $_.Name } |
        Select-Object Name, DisplayName, State, StartMode, PathName |
        Sort-Object Name)
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Recent Driver/System Events"
Add-Line ""
try {
    $query = "*[System[(Level=1 or Level=2 or Level=3) and TimeCreated[timediff(@SystemTime) <= 259200000]]]"
    $raw = & wevtutil.exe qe System /q:$query /c:40 /f:text 2>&1
    Add-Table ($raw |
        Select-String -Pattern "Hypervisor|Kernel-Power|Happ|NetBT|BTHUSB|TPM-WMI|Docker|disk|stor|Display|amdkmdag|atikmdag|WHEA|BugCheck" -Context 0,3 |
        ForEach-Object { [pscustomobject]@{ Line = $_.ToString() } })
}
catch {
    Add-Line "- Failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Local Verdict Hints"
Add-Line ""
Add-Line "- If `VirtualizationFirmwareEnabled` is `False`, Docker Desktop/WSL2/Kubernetes cannot be repaired from Windows; enable AMD-SVM/AMD-IOMMU in BIOS/UEFI first."
Add-Line "- If `HappService` is disabled and stopped, its repeated Service Control Manager errors should stop after restart."
Add-Line "- If tunnel adapters show repeated NetBT events, keep NetBIOS disabled on Xray/Wintun/TAP interfaces."
Add-Line "- Treat GPU/chipset driver updates as a restore-point task, not an automatic background action."
Add-Line ""

[System.IO.File]::WriteAllLines((Resolve-Path -LiteralPath $OutputDir).Path + "\windows-driver-audit-$stamp.md", $lines, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $outFile"
