param(
    [string]$OutputDir = "logs",
    [switch]$QuickScan
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outFile = Join-Path $OutputDir "windows-health-$stamp.md"
$lines = New-Object System.Collections.Generic.List[string]

function Add-Line([string]$Text = "") {
    $lines.Add($Text)
}

function Add-Table($Rows) {
    if ($null -eq $Rows) {
        Add-Line "_no data_"
        return
    }
    $text = ($Rows | Out-String -Width 260).TrimEnd()
    if ([string]::IsNullOrWhiteSpace($text)) {
        Add-Line "_no data_"
    }
    else {
        Add-Line '```text'
        Add-Line $text
        Add-Line '```'
    }
}

function Format-MB($Bytes) {
    if ($null -eq $Bytes) { return "0.0" }
    return ([math]::Round([double]$Bytes / 1MB, 1)).ToString("0.0")
}

Add-Line "# Windows Health Snapshot"
Add-Line ""
Add-Line "- Time: $(Get-Date -Format s)"
Add-Line "- Repo: $RepoRoot"
Add-Line "- Quick scan requested: $QuickScan"
Add-Line ""

Add-Line "## Memory"
Add-Line ""
try {
    Add-Type -AssemblyName Microsoft.VisualBasic | Out-Null
    $info = New-Object Microsoft.VisualBasic.Devices.ComputerInfo
    Add-Line "- Total physical RAM: $(Format-MB $info.TotalPhysicalMemory) MB"
    Add-Line "- Available physical RAM: $(Format-MB $info.AvailablePhysicalMemory) MB"
    Add-Line "- Used physical RAM: $([math]::Round((1 - ($info.AvailablePhysicalMemory / $info.TotalPhysicalMemory)) * 100, 1))%"
}
catch {
    Add-Line "- Memory probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Microsoft Defender"
Add-Line ""
try {
    $before = Get-MpComputerStatus
    Add-Line "### Status Before Scan"
    Add-Table ($before | Select-Object AMServiceEnabled, AntivirusEnabled, RealTimeProtectionEnabled, BehaviorMonitorEnabled, IoavProtectionEnabled, OnAccessProtectionEnabled, NISEnabled, QuickScanAge, FullScanAge, QuickScanStartTime, QuickScanEndTime, AntivirusSignatureLastUpdated, AMEngineVersion, AntivirusSignatureVersion)
    Add-Line ""

    if ($QuickScan) {
        Add-Line "### Quick Scan"
        Add-Line ""
        Add-Line "- Started: $(Get-Date -Format s)"
        try {
            Start-MpScan -ScanType QuickScan
            Add-Line "- Finished: $(Get-Date -Format s)"
        }
        catch {
            Add-Line "- Quick scan failed: $($_.Exception.Message)"
        }
        Add-Line ""
    }

    $after = Get-MpComputerStatus
    Add-Line "### Status After Scan"
    Add-Table ($after | Select-Object AMServiceEnabled, AntivirusEnabled, RealTimeProtectionEnabled, QuickScanAge, FullScanAge, QuickScanStartTime, QuickScanEndTime, AntivirusSignatureLastUpdated, AMEngineVersion, AntivirusSignatureVersion)
    Add-Line ""

    Add-Line "### Active Threats"
    $threats = Get-MpThreat | Select-Object ThreatName, SeverityID, CategoryID, DidThreatExecute, IsActive, Resources
    Add-Table $threats
    Add-Line ""

    Add-Line "### Recent Threat Detections"
    $detections = Get-MpThreatDetection |
        Sort-Object InitialDetectionTime -Descending |
        Select-Object -First 20 InitialDetectionTime, ThreatName, ActionSuccess, CurrentThreatExecutionStatusID, Resources
    Add-Table $detections
}
catch {
    Add-Line "- Defender probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Top RAM Processes"
Add-Line ""
try {
    $topRam = Get-Process -ErrorAction SilentlyContinue |
        Sort-Object WorkingSet64 -Descending |
        Select-Object -First 30 `
            @{Name = "RAM_MB"; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } },
            @{Name = "CPU_s"; Expression = { if ($_.CPU) { [math]::Round($_.CPU, 1) } else { 0 } } },
            Id, ProcessName, Path
    Add-Table $topRam
}
catch {
    Add-Line "- Process probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Dev And Heavy Command Lines"
Add-Line ""
try {
    $namePattern = "docker|wsl|vmmem|Code|python|node|git|MsMpEng|SearchIndexer|OneDrive|chrome|msedge|opera|browser"
    $devProcesses = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -match $namePattern -or $_.CommandLine -match "pylance|pytest|manage\.py|headroom|playwright|docker|wsl" } |
        Select-Object ProcessId, ParentProcessId, Name,
            @{Name = "RAM_MB"; Expression = { try { [math]::Round((Get-Process -Id $_.ProcessId -ErrorAction Stop).WorkingSet64 / 1MB, 1) } catch { 0 } } },
            CommandLine |
        Sort-Object RAM_MB -Descending
    Add-Table $devProcesses
}
catch {
    Add-Line "- Command-line probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Startup Commands"
Add-Line ""
try {
    $startup = Get-CimInstance Win32_StartupCommand |
        Select-Object Name, Command, Location, User |
        Sort-Object Name
    Add-Table $startup
}
catch {
    Add-Line "- Startup probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## WSL"
Add-Line ""
try {
    $wsl = & wsl.exe -l -v 2>&1
    Add-Line '```text'
    foreach ($line in $wsl) { Add-Line ([string]$line) }
    Add-Line '```'
}
catch {
    Add-Line "- WSL probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Recommendations"
Add-Line ""
Add-Line "- Keep Docker Desktop out of autostart until Docker work starts."
Add-Line "- Keep browser autostart entries off during dev sessions if RAM is below 1.5 GB free."
Add-Line "- Consider trusted Defender exclusions for generated dev folders only: .git, .venv, frontend/node_modules, Dolg_APP/ml/dataset/external, Dolg_APP/ml/dataset/hf_cache, backups, media."
Add-Line "- Move multi-GB ML datasets outside the active workspace or keep them behind VS Code watcher/search excludes."
Add-Line "- Restart Pylance after settings changes; it can keep old indexing state until restarted."

[System.IO.File]::WriteAllLines((Resolve-Path -LiteralPath $OutputDir).Path + "\windows-health-$stamp.md", $lines, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $outFile"
