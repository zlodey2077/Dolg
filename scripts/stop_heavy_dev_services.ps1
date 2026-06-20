param(
    [switch]$Apply,
    [switch]$IncludePlaywright,
    [switch]$IncludePylance,
    [switch]$IncludeTraining,
    [switch]$IncludeHeadroom,
    [switch]$IncludeCodeUpdater,
    [switch]$IncludeGit
)

$ErrorActionPreference = "Continue"

function Get-DevProcessCandidates {
    $processes = Get-CimInstance Win32_Process
    foreach ($proc in $processes) {
        $cmd = [string]$proc.CommandLine
        $name = [string]$proc.Name
        $reason = $null

        if ($name -eq "python.exe" -and ($cmd -match "manage\.py test" -or $cmd -match "pytest")) {
            $reason = "stale Django/pytest test process"
        }
        elseif ($IncludeTraining -and $name -eq "python.exe" -and ($cmd -match "train_tiny_circuit_ai" -or $cmd -match "train_tiny_model")) {
            $reason = "heavy Django AI training process"
        }
        elseif ($IncludeTraining -and $name -eq "powershell.exe" -and ($cmd -match "train_tiny_circuit_ai" -or $cmd -match "train_tiny_model")) {
            $reason = "heavy Django AI training launcher"
        }
        elseif ($IncludeTraining -and $name -eq "bash.exe" -and ($cmd -match "train_tiny_circuit_ai" -or $cmd -match "train_tiny_model")) {
            $reason = "heavy Django AI training launcher"
        }
        elseif ($name -eq "docker.exe" -and $cmd -match "context ls") {
            $reason = "stuck Docker context probe"
        }
        elseif ($name -eq "kubectl.exe" -and ($cmd -match "config\s+current-context" -or $cmd -match "kustomize\s+deploy/k8s")) {
            $reason = "stuck Kubernetes CLI probe"
        }
        elseif ($IncludePlaywright -and $name -eq "node.exe" -and $cmd -match "playwright-core.*cliDaemon") {
            $reason = "Playwright CLI daemon"
        }
        elseif ($IncludePylance -and $name -eq "Code.exe" -and $cmd -match "ms-python\.vscode-pylance.*server\.bundle\.js") {
            $reason = "Pylance language server"
        }
        elseif ($IncludeHeadroom -and $name -eq "python.exe" -and $cmd -match "headroom\.exe.*proxy") {
            $reason = "headroom proxy"
        }
        elseif ($IncludeCodeUpdater -and $name -like "CodeSetup-stable*") {
            $reason = "VS Code updater"
        }
        elseif ($name -eq "powershell.exe" -and $cmd -match "diagnose_system_load\.ps1") {
            $reason = "stuck system load diagnostic"
        }
        elseif ($IncludeGit -and $name -eq "git.exe") {
            $reason = "git process"
        }

        if ($reason) {
            [pscustomobject]@{
                ProcessId = $proc.ProcessId
                ParentProcessId = $proc.ParentProcessId
                Name = $name
                Reason = $reason
                CommandLine = $cmd
            }
        }
    }
}

$candidates = @(Get-DevProcessCandidates | Sort-Object @{ Expression = { if ($_.Reason -match "launcher") { 0 } else { 1 } } }, ParentProcessId, ProcessId)

if (-not $candidates) {
    Write-Host "No heavy dev process candidates found."
    exit 0
}

$candidates | Select-Object ProcessId, ParentProcessId, Name, Reason, CommandLine | Format-Table -AutoSize

if (-not $Apply) {
    Write-Host ""
    Write-Host "Dry run only. Re-run with -Apply to stop these processes."
    exit 0
}

function Test-TasklistProcessExists([int]$ProcessId) {
    $rows = @(tasklist.exe /FI "PID eq $ProcessId" /NH 2>$null)
    foreach ($row in $rows) {
        if ($row -match "^\s*\S+" -and $row -notmatch "No tasks are running") {
            return $true
        }
    }
    return $false
}

foreach ($candidate in $candidates) {
    try {
        $taskkillOutput = @(taskkill.exe /PID $candidate.ProcessId /T /F 2>&1)
        foreach ($line in $taskkillOutput) {
            if ($line) { Write-Host $line }
        }

        Start-Sleep -Milliseconds 500
        if (Test-TasklistProcessExists -ProcessId $candidate.ProcessId) {
            Stop-Process -Id $candidate.ProcessId -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 500
        }

        if (Test-TasklistProcessExists -ProcessId $candidate.ProcessId) {
            Write-Warning "Still present after termination attempt #$($candidate.ProcessId): $($candidate.Reason)"
        }
        else {
            Write-Host "Stopped #$($candidate.ProcessId): $($candidate.Reason)"
        }
    }
    catch {
        Write-Warning "Could not stop #$($candidate.ProcessId): $($_.Exception.Message)"
    }
}
