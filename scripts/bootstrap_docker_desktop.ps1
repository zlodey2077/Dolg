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

Write-Step "Checking docker-users membership"
$members = (cmd /c "net localgroup docker-users" 2>$null) -join "`n"
if ($members -notmatch [regex]::Escape($env:USERNAME)) {
    if (-not $isAdmin) {
        Write-Warning "Current user is not in docker-users. Relaunching this script as Administrator."
        $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-TimeoutSeconds", $TimeoutSeconds)
        if ($StartVisible) { $args += "-StartVisible" }
        Start-Process powershell.exe -Verb RunAs -ArgumentList $args
        exit 2
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
        Write-Warning "com.docker.service is $($service.Status); starting it requires UAC/Admin."
        Write-Warning "Relaunching this script as Administrator so the service can be started."
        $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-TimeoutSeconds", $TimeoutSeconds)
        if ($StartVisible) { $args += "-StartVisible" }
        Start-Process powershell.exe -Verb RunAs -ArgumentList $args
        exit 2
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
