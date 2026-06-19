param(
    [string]$OutputDir = "logs",
    [switch]$IncludeRepoScan
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outFile = Join-Path $OutputDir "system-load-$stamp.md"
$lines = New-Object System.Collections.Generic.List[string]

function Add-Line([string]$Text = "") {
    $lines.Add($Text)
}

function Format-MB($Bytes) {
    if ($null -eq $Bytes) { return "0.0" }
    return ([math]::Round([double]$Bytes / 1MB, 1)).ToString("0.0")
}

function Add-Table($Rows) {
    if ($null -eq $Rows) {
        Add-Line "_no data_"
        return
    }
    $text = ($Rows | Out-String -Width 240).TrimEnd()
    if ([string]::IsNullOrWhiteSpace($text)) {
        Add-Line "_no data_"
    }
    else {
        Add-Line '```text'
        Add-Line $text
        Add-Line '```'
    }
}

Add-Line "# System Load Snapshot"
Add-Line ""
Add-Line "- Time: $(Get-Date -Format s)"
Add-Line "- Repo: $RepoRoot"
Add-Line ""

try {
    Add-Type -AssemblyName Microsoft.VisualBasic | Out-Null
    $info = New-Object Microsoft.VisualBasic.Devices.ComputerInfo
    Add-Line "## Memory"
    Add-Line ""
    Add-Line "- Total physical RAM: $(Format-MB $info.TotalPhysicalMemory) MB"
    Add-Line "- Available physical RAM: $(Format-MB $info.AvailablePhysicalMemory) MB"
    Add-Line "- Used physical RAM: $([math]::Round((1 - ($info.AvailablePhysicalMemory / $info.TotalPhysicalMemory)) * 100, 1))%"
    Add-Line ""
}
catch {
    Add-Line "## Memory"
    Add-Line ""
    Add-Line "- Memory probe failed: $($_.Exception.Message)"
    Add-Line ""
}

Add-Line "## Drives"
Add-Line ""
try {
    $drives = [System.IO.DriveInfo]::GetDrives() |
        Where-Object { $_.IsReady -and $_.DriveType -eq "Fixed" } |
        Select-Object Name,
            @{Name = "TotalGB"; Expression = { [math]::Round($_.TotalSize / 1GB, 1) } },
            @{Name = "FreeGB"; Expression = { [math]::Round($_.AvailableFreeSpace / 1GB, 1) } },
            @{Name = "FreePct"; Expression = { [math]::Round($_.AvailableFreeSpace / $_.TotalSize * 100, 1) } }
    Add-Table $drives
}
catch {
    Add-Line "- Drive probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Top RAM Processes"
Add-Line ""
$topRam = Get-Process -ErrorAction SilentlyContinue |
    Sort-Object WorkingSet64 -Descending |
    Select-Object -First 30 `
        @{Name = "RAM_MB"; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } },
        @{Name = "CPU_s"; Expression = { if ($_.CPU) { [math]::Round($_.CPU, 1) } else { 0 } } },
        Id, ProcessName, Path
Add-Table $topRam
Add-Line ""

Add-Line "## Top Cumulative CPU Processes"
Add-Line ""
$topCpu = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $null -ne $_.CPU } |
    Sort-Object CPU -Descending |
    Select-Object -First 30 `
        @{Name = "CPU_s"; Expression = { [math]::Round($_.CPU, 1) } },
        @{Name = "RAM_MB"; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 1) } },
        Id, ProcessName, Path
Add-Table $topCpu
Add-Line ""

Add-Line "## Dev-Heavy Process Command Lines"
Add-Line ""
$targetNames = @(
    "python.exe",
    "node.exe",
    "git.exe",
    "docker.exe",
    "com.docker.backend.exe",
    "Docker Desktop.exe",
    "wsl.exe",
    "wslservice.exe",
    "vmmem.exe",
    "Code.exe",
    "codex.exe"
)
try {
    $devProcesses = Get-CimInstance Win32_Process |
        Where-Object { $targetNames -contains $_.Name } |
        Select-Object ProcessId, ParentProcessId, Name,
            @{Name = "RAM_MB"; Expression = { [math]::Round(($_.WorkingSetSize / 1MB), 1) } },
            CommandLine |
        Sort-Object Name, ProcessId
    Add-Table $devProcesses
}
catch {
    Add-Line "- Command-line probe failed: $($_.Exception.Message)"
}
Add-Line ""

Add-Line "## Repo Heavy Paths"
Add-Line ""
$repoPaths = @(
    "Dolg_APP/ml",
    "Dolg_APP/ml/dataset/external",
    "backups",
    "media",
    ".venv",
    "frontend/node_modules",
    ".git"
)
if ($IncludeRepoScan) {
    $rows = foreach ($path in $repoPaths) {
        if (Test-Path -LiteralPath $path) {
            $sw = [Diagnostics.Stopwatch]::StartNew()
            $count = 0
            $size = 0L
            try {
                Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue |
                    ForEach-Object {
                        $count++
                        $size += $_.Length
                    }
                $complete = $true
            }
            catch {
                $complete = $false
            }
            $sw.Stop()
            [pscustomobject]@{
                Path = $path
                Files = $count
                SizeMB = [math]::Round($size / 1MB, 1)
                ScanSec = [math]::Round($sw.Elapsed.TotalSeconds, 2)
                Complete = $complete
            }
        }
    }
    Add-Table ($rows | Sort-Object SizeMB -Descending)
}
else {
    $rows = foreach ($path in $repoPaths) {
        [pscustomobject]@{
            Path = $path
            Exists = Test-Path -LiteralPath $path
            Note = "recursive size skipped; run with -IncludeRepoScan only when needed"
        }
    }
    Add-Table $rows
}
Add-Line ""

Add-Line "## Verdict Hints"
Add-Line ""
Add-Line "- If `Dolg_APP/ml/dataset/external` is multi-GB, exclude it from VS Code watchers/search and avoid broad recursive scans."
Add-Line "- If stale `manage.py test`, `pytest`, `docker context ls`, or Playwright daemon processes exist, stop them before heavy checks."
Add-Line "- Keep Docker Desktop off until the product task actually needs Docker."

[System.IO.File]::WriteAllLines((Resolve-Path -LiteralPath $OutputDir).Path + "\system-load-$stamp.md", $lines, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $outFile"
