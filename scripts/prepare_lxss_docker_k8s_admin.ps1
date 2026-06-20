param(
    [int]$DockerTimeoutSeconds = 300,
    [switch]$EnableFullHyperV,
    [switch]$InstallUbuntu,
    [switch]$ResetDockerRuntime,
    [switch]$SkipDockerDesktopSettings
)

$ErrorActionPreference = "Continue"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir ("lxss-docker-k8s-prepare-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

Start-Transcript -Path $LogPath -Append | Out-Null

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "== $Message =="
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-ElevatedSelf {
    $args = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "`"$PSCommandPath`"",
        "-DockerTimeoutSeconds",
        $DockerTimeoutSeconds
    )
    if ($EnableFullHyperV) { $args += "-EnableFullHyperV" }
    if ($InstallUbuntu) { $args += "-InstallUbuntu" }
    if ($ResetDockerRuntime) { $args += "-ResetDockerRuntime" }
    if ($SkipDockerDesktopSettings) { $args += "-SkipDockerDesktopSettings" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $args
}

function Enable-FeatureIfNeeded([string]$Name) {
    try {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $Name -ErrorAction Stop
        if ($feature.State -eq "Enabled") {
            Write-Host "${Name}: Enabled"
            return
        }
        Write-Host "${Name}: $($feature.State). Enabling..."
        $result = Enable-WindowsOptionalFeature -Online -FeatureName $Name -All -NoRestart -ErrorAction Stop
        if ($result.RestartNeeded) {
            $script:RestartRequired = $true
        }
    }
    catch {
        Write-Warning "Could not enable ${Name}: $($_.Exception.Message)"
    }
}

function Start-ServiceSafe([string]$Name) {
    try {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status -ne "Running") {
            Start-Service -Name $Name -ErrorAction Stop
            Start-Sleep -Seconds 1
            $service.Refresh()
        }
        Write-Host "${Name}: $($service.Status)"
        return $true
    }
    catch {
        Write-Warning "Could not start ${Name}: $($_.Exception.Message)"
        return $false
    }
}

function Invoke-ProcessWithTimeout {
    param(
        [string]$FilePath,
        [string]$Arguments,
        [int]$TimeoutSeconds = 15
    )
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $Arguments
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    try {
        $process = [System.Diagnostics.Process]::Start($startInfo)
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-ProcessTree -ProcessId $process.Id
            return @{ Ok = $false; TimedOut = $true; Output = "$FilePath $Arguments timed out" }
        }
        $out = $process.StandardOutput.ReadToEnd().Trim()
        $err = $process.StandardError.ReadToEnd().Trim()
        return @{ Ok = ($process.ExitCode -eq 0); TimedOut = $false; Output = (($out, $err) -join " ").Trim() }
    }
    catch {
        return @{ Ok = $false; TimedOut = $false; Output = $_.Exception.Message }
    }
}

function Get-ChildProcessIds {
    param([int]$ProcessId)

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        Get-ChildProcessIds -ProcessId $child.ProcessId
        $child.ProcessId
    }
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $ids = @(Get-ChildProcessIds -ProcessId $ProcessId)
    [array]::Reverse($ids)
    foreach ($id in $ids) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-DockerCliProcesses {
    $names = @(
        "com.docker.backend",
        "com.docker.build",
        "com.docker.proxy",
        "Docker Desktop",
        "docker",
        "docker-agent",
        "docker-ai",
        "docker-buildx",
        "docker-compose",
        "docker-debug",
        "docker-desktop",
        "docker-dhi",
        "docker-extension",
        "docker-init",
        "docker-mcp",
        "docker-model",
        "docker-offload",
        "docker-pass",
        "docker-sandbox",
        "docker-sbom",
        "docker-scout",
        "vpnkit"
    )
    Get-Process -Name $names -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

function Test-HardwareVirtualization {
    Write-Step "Check hardware virtualization"
    try {
        $cpu = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
        if (-not $cpu) {
            Write-Warning "CPU information is unavailable. Continuing, but Docker Desktop may fail."
            return $true
        }

        Write-Host "CPU: $($cpu.Name)"
        Write-Host "VM monitor extensions: $($cpu.VMMonitorModeExtensions)"
        Write-Host "SLAT: $($cpu.SecondLevelAddressTranslationExtensions)"
        Write-Host "Virtualization enabled in firmware: $($cpu.VirtualizationFirmwareEnabled)"

        if ($cpu.VMMonitorModeExtensions -eq $false -or $cpu.SecondLevelAddressTranslationExtensions -eq $false) {
            Write-Warning "This CPU does not report the virtualization features required by Docker Desktop."
            return $false
        }
        if ($cpu.VirtualizationFirmwareEnabled -eq $false) {
            Write-Warning "Hardware virtualization is disabled in BIOS/UEFI. Enable AMD-SVM/AMD-IOMMU or Intel VT-x/VT-d, save with F10, boot Windows, then re-run this script."
            return $false
        }

        $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
        if ($computer -and $computer.HypervisorPresent -eq $false) {
            Write-Warning "Firmware virtualization is enabled, but Windows hypervisor is not currently loaded. A reboot may still be required after this script."
        }
        return $true
    }
    catch {
        Write-Warning "Could not check hardware virtualization: $($_.Exception.Message)"
        return $true
    }
}

function Set-JsonProperty($Object, [string]$Name, $Value) {
    $existing = $Object.PSObject.Properties[$Name]
    if ($existing) {
        $existing.Value = $Value
    }
    else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function Update-DockerDesktopSettings {
    if ($SkipDockerDesktopSettings) {
        Write-Host "Docker Desktop settings update skipped."
        return
    }

    $candidates = @(
        (Join-Path $env:APPDATA "Docker\settings.json"),
        (Join-Path $env:APPDATA "Docker\settings-store.json")
    )

    foreach ($path in $candidates) {
        if (-not (Test-Path -LiteralPath $path)) {
            continue
        }
        try {
            $raw = Get-Content -LiteralPath $path -Raw
            if ([string]::IsNullOrWhiteSpace($raw)) {
                continue
            }
            $json = $raw | ConvertFrom-Json
            $changed = $false
            foreach ($key in @("kubernetesEnabled", "enableKubernetes")) {
                if ($json.PSObject.Properties[$key]) {
                    Set-JsonProperty $json $key $true
                    $changed = $true
                }
            }
            foreach ($key in @("EnableDockerAI", "DockerAIEnabled", "enableDockerAI")) {
                if ($json.PSObject.Properties[$key]) {
                    Set-JsonProperty $json $key $false
                    $changed = $true
                }
            }
            if ($changed) {
                $backup = "$path.bak-$(Get-Date -Format "yyyyMMdd-HHmmss")"
                Copy-Item -LiteralPath $path -Destination $backup
                [System.IO.File]::WriteAllText($path, ($json | ConvertTo-Json -Depth 50) + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
                Write-Host "Updated Docker Desktop settings: $path"
                Write-Host "Backup: $backup"
            }
            else {
                Write-Host "No known managed setting key found in $path"
            }
        }
        catch {
            Write-Warning "Could not update ${path}: $($_.Exception.Message)"
        }
    }
}

function Backup-And-MovePath {
    param(
        [string]$Path,
        [string]$BackupRoot
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $resolvedDockerLocal = (Resolve-Path -LiteralPath (Join-Path $env:LOCALAPPDATA "Docker")).Path
    if (-not $resolvedPath.StartsWith($resolvedDockerLocal, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to move path outside Docker local data root: $resolvedPath"
    }
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        New-Item -ItemType Directory -Path $BackupRoot | Out-Null
    }
    $target = Join-Path $BackupRoot (Split-Path -Leaf $resolvedPath)
    try {
        Move-Item -LiteralPath $resolvedPath -Destination $target -ErrorAction Stop
        Write-Host "Moved $resolvedPath -> $target"
    }
    catch {
        Write-Warning "Could not move ${resolvedPath}: $($_.Exception.Message)"
    }
}

function Reset-DockerRuntimeCache {
    if (-not $ResetDockerRuntime) {
        return
    }

    Write-Step "Reset Docker Desktop runtime cache"
    Write-Warning "ResetDockerRuntime is enabled. Docker Desktop runtime/cache paths will be moved to backup folders, not deleted."
    try {
        wsl.exe --shutdown 2>$null
    }
    catch {
    }
    foreach ($distro in @("docker-desktop", "docker-desktop-data")) {
        try {
            wsl.exe --unregister $distro 2>$null
            Write-Host "Unregistered WSL distro if present: $distro"
        }
        catch {
        }
    }
    foreach ($name in @("com.docker.service")) {
        Stop-Service -Name $name -Force -ErrorAction SilentlyContinue
    }
    Stop-DockerCliProcesses
    Get-Process -Name "docker", "Docker Desktop", "com.docker.backend", "com.docker.build", "com.docker.proxy", "docker-sandbox", "vpnkit", "docker-offload" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue

    Start-Sleep -Seconds 2
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $dockerLocal = Join-Path $env:LOCALAPPDATA "Docker"
    $backupRoot = Join-Path $dockerLocal ("reset-backup-$stamp")
    foreach ($path in @(
        (Join-Path $dockerLocal "wsl"),
        (Join-Path $dockerLocal "run"),
        (Join-Path $dockerLocal "tasks"),
        (Join-Path $dockerLocal "backend.lock"),
        (Join-Path $dockerLocal "frontend.lock"),
        (Join-Path $dockerLocal "launcher.lock"),
        (Join-Path $dockerLocal "backendstacks.log")
    )) {
        Backup-And-MovePath -Path $path -BackupRoot $backupRoot
    }
    Write-Host "Docker runtime backup root: $backupRoot"
}

function Test-DockerReady {
    $result = Invoke-ProcessWithTimeout "docker.exe" 'info --format "{{.ServerVersion}} {{.OperatingSystem}}"' 10
    if ($result.Ok) {
        Write-Host "Docker Engine is ready: $($result.Output)"
        return $true
    }
    if ($result.TimedOut) {
        Stop-DockerCliProcesses
    }
    Write-Host "Docker Engine not ready: $($result.Output)"
    return $false
}

if (-not (Test-IsAdmin)) {
    Write-Warning "This preparation must run as Administrator. Relaunching with UAC..."
    Stop-Transcript | Out-Null
    Invoke-ElevatedSelf
    exit 2
}

$script:RestartRequired = $false

Write-Host "DOLG Lxss/Docker/Kubernetes preparation"
Write-Host "Root: $RepoRoot"
Write-Host "Log: $LogPath"
Write-Host "InstallUbuntu: $InstallUbuntu"
Write-Host "ResetDockerRuntime: $ResetDockerRuntime"

Write-Step "Stop stale Docker processes"
Stop-DockerCliProcesses
Get-Process -Name "docker", "Docker Desktop", "com.docker.backend", "com.docker.build", "com.docker.proxy", "docker-sandbox", "vpnkit" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
if (-not (Test-HardwareVirtualization)) {
    Write-Warning "Docker preparation stopped before Engine startup because virtualization is disabled in firmware."
    Stop-DockerCliProcesses
    Stop-Transcript | Out-Null
    exit 3
}
Reset-DockerRuntimeCache

Write-Step "Enable Windows virtualization features"
Enable-FeatureIfNeeded "Microsoft-Windows-Subsystem-Linux"
Enable-FeatureIfNeeded "VirtualMachinePlatform"
Enable-FeatureIfNeeded "HypervisorPlatform"
if ($EnableFullHyperV) {
    Enable-FeatureIfNeeded "Microsoft-Hyper-V-All"
}
else {
    Write-Host "Microsoft-Hyper-V-All skipped. Use -EnableFullHyperV only if Docker Desktop still cannot start."
}

Write-Step "Set hypervisor boot and service timeout"
try {
    bcdedit /set hypervisorlaunchtype auto | Out-Host
}
catch {
    Write-Warning "Could not set hypervisorlaunchtype: $($_.Exception.Message)"
}
try {
    New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control" -Name "ServicesPipeTimeout" -Value 180000 -PropertyType DWord -Force | Out-Null
    Write-Host "ServicesPipeTimeout: 180000 ms"
}
catch {
    Write-Warning "Could not set ServicesPipeTimeout: $($_.Exception.Message)"
}

Write-Step "Start Lxss/VM/network services"
Start-ServiceSafe "hns" | Out-Null
Start-ServiceSafe "vmcompute" | Out-Null
Start-ServiceSafe "LxssManager" | Out-Null
Start-ServiceSafe "com.docker.service" | Out-Null

Write-Step "Refresh WSL status"
$wslStatus = Invoke-ProcessWithTimeout "wsl.exe" "--status" 30
Write-Host $wslStatus.Output
if (-not $wslStatus.Ok -or $wslStatus.Output -match "wsl --update|wsl2kernel|0x800") {
    foreach ($args in @("--update", "--update --web-download", "--update --inbox")) {
        Write-Host "Trying: wsl $args"
        $update = Invoke-ProcessWithTimeout "wsl.exe" $args 180
        Write-Host $update.Output
        if ($update.Ok) { break }
    }
}
Invoke-ProcessWithTimeout "wsl.exe" "--set-default-version 2" 30 | Out-Null

Write-Step "Check WSL distributions"
$wslList = Invoke-ProcessWithTimeout "wsl.exe" "-l -q" 30
if ($wslList.Ok -and -not [string]::IsNullOrWhiteSpace($wslList.Output)) {
    Write-Host $wslList.Output
}
else {
    Write-Warning "No regular WSL distro is installed. Docker Desktop can still create its own docker-desktop distro when Engine starts."
    if ($InstallUbuntu) {
        Write-Host "Installing Ubuntu through WSL..."
        $install = Invoke-ProcessWithTimeout "wsl.exe" "--install -d Ubuntu" 900
        Write-Host $install.Output
        $script:RestartRequired = $true
    }
    else {
        Write-Host "Ubuntu install skipped. Re-run with -InstallUbuntu only if you need an interactive Linux distro."
    }
}

Write-Step "Ensure docker-users membership"
$members = (cmd.exe /c "net localgroup docker-users" 2>$null) -join "`n"
if ($members -notmatch [regex]::Escape($env:USERNAME)) {
    cmd.exe /c "net localgroup docker-users `"$env:USERNAME`" /add" | Out-Host
    Write-Warning "User was added to docker-users. Sign out/in if Docker still refuses access."
}
else {
    Write-Host "docker-users: OK"
}

Write-Step "Prepare kubeconfig directory"
$kubeDir = Join-Path $env:USERPROFILE ".kube"
if (-not (Test-Path -LiteralPath $kubeDir)) {
    New-Item -ItemType Directory -Path $kubeDir | Out-Null
}
Write-Host "Kubeconfig path: $(Join-Path $kubeDir "config")"

Write-Step "Prepare Docker Desktop settings"
Update-DockerDesktopSettings

if ($RestartRequired) {
    Write-Host ""
    Write-Warning "Restart Windows before testing Docker Desktop again."
    Stop-Transcript | Out-Null
    exit 2
}

Write-Step "Start Docker Desktop"
$dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
if (-not (Test-Path -LiteralPath $dockerDesktop)) {
    Write-Error "Docker Desktop executable was not found: $dockerDesktop"
    Stop-Transcript | Out-Null
    exit 1
}
Start-Process -FilePath $dockerDesktop

Write-Step "Wait for Docker Engine"
$deadline = (Get-Date).AddSeconds($DockerTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-DockerReady) {
        break
    }
    Start-Sleep -Seconds 5
}

if (-not (Test-DockerReady)) {
    Write-Warning "Docker Engine is still not ready. Open Docker Desktop and finish first-run/WSL prompts, then run this script again."
    Stop-Transcript | Out-Null
    exit 3
}

Write-Step "Check Kubernetes context"
$context = Invoke-ProcessWithTimeout "kubectl.exe" "config current-context" 15
if ($context.Ok -and $context.Output) {
    Write-Host "Current context: $($context.Output)"
}
else {
    Write-Warning "No Kubernetes context yet. Enable Docker Desktop > Settings > Kubernetes > Enable Kubernetes, Apply & Restart."
    Write-Host "After Kubernetes starts, run: kubectl config use-context docker-desktop"
}

Write-Step "Final stack check"
Set-Location $RepoRoot
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts\check_vscode_stacks.ps1")

Stop-Transcript | Out-Null
