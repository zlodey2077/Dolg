param(
    [int]$DockerTimeoutSeconds = 300,
    [switch]$EnableFullHyperV,
    [switch]$InstallUbuntu,
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
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
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
            if ($changed) {
                $backup = "$path.bak-$(Get-Date -Format "yyyyMMdd-HHmmss")"
                Copy-Item -LiteralPath $path -Destination $backup
                [System.IO.File]::WriteAllText($path, ($json | ConvertTo-Json -Depth 50) + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
                Write-Host "Updated Docker Desktop Kubernetes setting: $path"
                Write-Host "Backup: $backup"
            }
            else {
                Write-Host "No known Kubernetes setting key found in $path"
            }
        }
        catch {
            Write-Warning "Could not update ${path}: $($_.Exception.Message)"
        }
    }
}

function Test-DockerReady {
    $result = Invoke-ProcessWithTimeout "docker.exe" 'info --format "{{.ServerVersion}} {{.OperatingSystem}}"' 10
    if ($result.Ok) {
        Write-Host "Docker Engine is ready: $($result.Output)"
        return $true
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

Write-Step "Stop stale Docker processes"
Get-Process -Name "docker", "Docker Desktop", "com.docker.backend", "com.docker.build", "com.docker.proxy", "docker-sandbox", "vpnkit" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

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
