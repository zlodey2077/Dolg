param(
    [int]$TimeoutSeconds = 180,
    [switch]$StartVisible,
    [switch]$InstallIfMissing
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message"
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-ElevatedSelf($Reason) {
    Write-Warning $Reason
    Write-Warning "Relaunching this script as Administrator."
    $args = @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-TimeoutSeconds", $TimeoutSeconds)
    if ($StartVisible) { $args += "-StartVisible" }
    if ($InstallIfMissing) { $args += "-InstallIfMissing" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $args
    exit 2
}

function Enable-WindowsFeatureIfNeeded($FeatureName) {
    $feature = Get-WindowsOptionalFeature -Online -FeatureName $FeatureName -ErrorAction Stop
    if ($feature.State -eq "Enabled") {
        Write-Host "${FeatureName}: Enabled"
        return $false
    }

    Write-Warning "${FeatureName}: $($feature.State); enabling it now."
    $result = Enable-WindowsOptionalFeature -Online -FeatureName $FeatureName -All -NoRestart -ErrorAction Stop
    return [bool]$result.RestartNeeded
}

function Invoke-CommandWithTimeout($FileName, $Arguments, [int]$TimeoutMs = 120000) {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FileName
    $startInfo.Arguments = $Arguments
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    $process = [System.Diagnostics.Process]::Start($startInfo)
    if (-not $process.WaitForExit($TimeoutMs)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        return @{ Ok = $false; ExitCode = -1; Output = "$FileName $Arguments timed out" }
    }
    $out = $process.StandardOutput.ReadToEnd().Trim()
    $err = $process.StandardError.ReadToEnd().Trim()
    return @{ Ok = ($process.ExitCode -eq 0); ExitCode = $process.ExitCode; Output = (($out, $err) -join " ").Trim() }
}

function Install-WslKernelMsi($IsAdmin) {
    $msi = Join-Path $env:TEMP "wsl_update_x64.msi"
    $uris = @(
        "https://aka.ms/wsl2kernel",
        "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
    )

    foreach ($uri in $uris) {
        Write-Warning "Downloading WSL2 kernel MSI from $uri"
        Remove-Item -LiteralPath $msi -Force -ErrorAction SilentlyContinue
        $progressPreferenceBefore = $ProgressPreference
        $ProgressPreference = "SilentlyContinue"
        try {
            Invoke-WebRequest -Uri $uri -OutFile $msi -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
            if ((Test-Path $msi) -and (Get-Item $msi).Length -gt 1MB) {
                break
            }
            Write-Warning "Downloaded MSI is missing or too small."
        }
        catch {
            Write-Warning "Could not download WSL2 kernel MSI from ${uri}: $($_.Exception.Message)"
        }
        finally {
            $ProgressPreference = $progressPreferenceBefore
        }
    }

    if (-not (Test-Path $msi) -or (Get-Item $msi).Length -le 1MB) {
        throw "WSL2 kernel MSI was not downloaded. Open https://aka.ms/wsl2kernel in a browser, install the x64 MSI, restart Windows, then run this script again."
    }

    if ($IsAdmin) {
        $process = Start-Process msiexec.exe -ArgumentList @("/i", "`"$msi`"", "/quiet", "/norestart") -Wait -PassThru
    }
    else {
        $process = Start-Process msiexec.exe -Verb RunAs -ArgumentList @("/i", "`"$msi`"", "/passive", "/norestart") -Wait -PassThru
    }

    if ($process.ExitCode -notin @(0, 3010)) {
        throw "WSL2 kernel MSI failed with exit code $($process.ExitCode)."
    }
    if ($process.ExitCode -eq 3010) {
        Write-Warning "WSL2 kernel MSI installed and Windows asks for a restart."
    }
}

function Update-WslKernelIfNeeded($IsAdmin) {
    Write-Step "Checking WSL2 kernel update state"
    $status = Invoke-CommandWithTimeout "wsl.exe" "--status" 30000
    if ($status.Ok -and $status.Output -notmatch "wsl --update|WSL 2.*not found|wsl2kernel|0x800") {
        Write-Host "WSL status: OK"
        return
    }

    Write-Warning "WSL reports that the WSL2 kernel needs an update."
    if ($status.Output) {
        Write-Host $status.Output
    }

    foreach ($args in @("--update", "--update --web-download", "--update --inbox")) {
        Write-Host "Trying: wsl $args"
        $result = Invoke-CommandWithTimeout "wsl.exe" $args 180000
        if ($result.Ok) {
            Write-Host "WSL update completed with: wsl $args"
            wsl --shutdown 2>$null
            return
        }
        Write-Warning "wsl $args failed: $($result.Output)"
    }

    Install-WslKernelMsi $IsAdmin
    wsl --shutdown 2>$null
}

function Repair-WslBackendIfNeeded($IsAdmin) {
    $requiredServices = @("LxssManager", "vmcompute", "hns")
    $missingServices = @(
        foreach ($name in $requiredServices) {
            if (-not (Get-Service -Name $name -ErrorAction SilentlyContinue)) {
                $name
            }
        }
    )

    if ($missingServices.Count -eq 0) {
        foreach ($name in $requiredServices) {
            $service = Get-Service -Name $name -ErrorAction SilentlyContinue
            if ($service.Status -ne "Running") {
                if (-not $IsAdmin) {
                    Invoke-ElevatedSelf "Windows WSL/VM backend service ${name} is $($service.Status); starting it requires UAC/Admin."
                }
                Write-Warning "${name}: $($service.Status); starting it now."
                Start-Service -Name $name -ErrorAction Stop
                $service = Get-Service -Name $name -ErrorAction SilentlyContinue
            }
            Write-Host "${name}: $($service.Status)"
        }
        return
    }

    $missingText = $missingServices -join ", "
    if (-not $IsAdmin) {
        Invoke-ElevatedSelf "Windows WSL/VM backend services are missing: $missingText."
    }

    Write-Warning "Windows WSL/VM backend services are missing: $missingText."
    Write-Step "Enabling WSL2 and virtualization Windows features"
    $restartNeeded = $false
    foreach ($feature in @("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform", "HypervisorPlatform")) {
        try {
            if (Enable-WindowsFeatureIfNeeded $feature) {
                $restartNeeded = $true
            }
        }
        catch {
            Write-Warning "Could not inspect or enable ${feature}: $($_.Exception.Message)"
        }
    }

    try {
        bcdedit /set hypervisorlaunchtype auto | Out-Host
    }
    catch {
        Write-Warning "Could not set hypervisorlaunchtype=auto: $($_.Exception.Message)"
    }

    try {
        wsl --set-default-version 2 | Out-Host
    }
    catch {
        Write-Warning "Could not set WSL default version to 2 yet: $($_.Exception.Message)"
    }

    $stillMissing = @(
        foreach ($name in $requiredServices) {
            if (-not (Get-Service -Name $name -ErrorAction SilentlyContinue)) {
                $name
            }
        }
    )
    if ($restartNeeded -or $stillMissing.Count -gt 0) {
        throw "WSL/virtualization components were enabled or repaired. Restart Windows, start Docker Desktop, then run this script again."
    }
}

function Invoke-DockerInfoOnce {
    $stdout = New-TemporaryFile
    $stderr = New-TemporaryFile
    try {
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = "docker"
        $startInfo.Arguments = 'info --format "{{.ServerVersion}} {{.OperatingSystem}}"'
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.UseShellExecute = $false
        $process = [System.Diagnostics.Process]::Start($startInfo)
        if (-not $process.WaitForExit(8000)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            return @{ Ok = $false; Output = "docker info timed out" }
        }
        $out = $process.StandardOutput.ReadToEnd().Trim()
        $err = $process.StandardError.ReadToEnd().Trim()
        return @{ Ok = ($process.ExitCode -eq 0); Output = (($out, $err) -join " ").Trim() }
    }
    finally {
        Remove-Item $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

$desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
$isAdmin = Test-IsAdmin

Write-Step "Checking Docker Desktop installation"
if (-not (Test-Path $desktop)) {
    if (-not $InstallIfMissing) {
        throw "Docker Desktop is not installed. Re-run with -InstallIfMissing or install Docker Desktop first."
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is not available; install Docker Desktop manually."
    }
    winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements
}

Write-Host "Docker Desktop: $desktop"
Write-Host "Current user: $env:USERNAME"
Write-Host "Admin shell: $isAdmin"

Write-Step "Checking WSL2/VM backend prerequisites"
Repair-WslBackendIfNeeded $isAdmin
Update-WslKernelIfNeeded $isAdmin

Write-Step "Checking docker-users membership"
$members = (cmd /c "net localgroup docker-users" 2>$null) -join "`n"
if ($members -notmatch [regex]::Escape($env:USERNAME)) {
    if (-not $isAdmin) {
        Invoke-ElevatedSelf "Current user is not in docker-users."
    }
    cmd /c "net localgroup docker-users `"$env:USERNAME`" /add"
    Write-Warning "User was added to docker-users. Sign out/in if Docker still refuses access."
}
else {
    Write-Host "docker-users: OK"
}

Write-Step "Starting Docker Desktop service when possible"
$service = Get-Service com.docker.service -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne "Running") {
    if ($isAdmin) {
        Start-Service com.docker.service
        Write-Host "com.docker.service started."
    }
    else {
        Invoke-ElevatedSelf "com.docker.service is $($service.Status); starting it requires UAC/Admin."
    }
}

Write-Step "Starting Docker Desktop"
if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    if ($StartVisible) {
        Start-Process -FilePath $desktop
    }
    else {
        Start-Process -FilePath $desktop -WindowStyle Hidden
    }
}
else {
    Write-Host "Docker Desktop process already exists."
}

Write-Step "Waiting for Docker Engine"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    $result = Invoke-DockerInfoOnce
    if ($result.Ok) {
        Write-Host "Docker Engine is ready: $($result.Output)"
        docker compose version
        exit 0
    }
    Write-Host "waiting: $($result.Output)"
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)

throw "Docker Engine did not become ready within $TimeoutSeconds seconds. Open Docker Desktop and finish first-run setup/WSL prompts, then run this script again."
