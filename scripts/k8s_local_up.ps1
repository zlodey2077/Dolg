param(
    [string]$Image = "dolg:local",
    [string]$Namespace = "dolg",
    [int]$TimeoutSeconds = 300,
    [switch]$NoBuild,
    [switch]$NoWait,
    [switch]$PortForward,
    [int]$LocalPort = 8080,
    [string]$KindCluster = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$K8sDir = Join-Path $RepoRoot "deploy/k8s"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    Write-Host ""
    Write-Host "> $FilePath $($ArgumentList -join ' ')"
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
    }
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-DockerReady {
    if (-not (Test-CommandAvailable "docker")) {
        return $false
    }
    $stdout = New-TemporaryFile
    $stderr = New-TemporaryFile
    try {
        $process = Start-Process `
            -FilePath "docker" `
            -ArgumentList @("info", "--format", "{{.ServerVersion}}") `
            -NoNewWindow `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -PassThru
        if (-not $process.WaitForExit(8000)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            return $false
        }
        return $process.ExitCode -eq 0
    }
    finally {
        Remove-Item $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

function Test-KubectlReady {
    if (-not (Test-CommandAvailable "kubectl")) {
        throw "kubectl was not found in PATH. Enable Docker Desktop Kubernetes or install kubectl."
    }

    $stdout = New-TemporaryFile
    $stderr = New-TemporaryFile
    try {
        $process = Start-Process `
            -FilePath "kubectl" `
            -ArgumentList @("version", "--client=true") `
            -NoNewWindow `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -PassThru
        if (-not $process.WaitForExit(8000)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            throw "kubectl client check timed out."
        }
        if ($process.ExitCode -ne 0) {
            throw "kubectl client check failed: $(Get-Content $stderr -Raw)"
        }
    }
    finally {
        Remove-Item $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

Set-Location $RepoRoot

if (-not (Test-DockerReady)) {
    Write-Warning "Docker Engine is not ready. Trying Docker Desktop bootstrap first."
    & (Join-Path $RepoRoot "scripts/bootstrap_docker_desktop.ps1") -TimeoutSeconds 180 -StartVisible
    if (-not (Test-DockerReady)) {
        throw "Docker Engine is still not ready. Finish Docker Desktop/WSL startup, then rerun this script."
    }
}

Test-KubectlReady

if (Test-Path (Join-Path $RepoRoot ".venv/Scripts/python.exe")) {
    $Python = Join-Path $RepoRoot ".venv/Scripts/python.exe"
}
else {
    $Python = "python"
}

Invoke-Checked $Python @("scripts/check_k8s_static.py")
Invoke-Checked "kubectl" @("kustomize", $K8sDir)

if (-not $NoBuild) {
    Invoke-Checked "docker" @("build", "-f", "deploy/Dockerfile", "-t", $Image, ".")
}

if ($KindCluster) {
    if (-not (Test-CommandAvailable "kind")) {
        throw "kind was requested but the kind CLI was not found in PATH."
    }
    Invoke-Checked "kind" @("load", "docker-image", $Image, "--name", $KindCluster)
}

Invoke-Checked "kubectl" @("apply", "-k", $K8sDir)

if (-not $NoWait) {
    $timeout = "${TimeoutSeconds}s"
    Invoke-Checked "kubectl" @("-n", $Namespace, "wait", "--for=condition=complete", "job/dolg-migrate", "--timeout=$timeout")
    Invoke-Checked "kubectl" @("-n", $Namespace, "rollout", "status", "deploy/dolg-web", "--timeout=$timeout")
    Invoke-Checked "kubectl" @("-n", $Namespace, "rollout", "status", "deploy/dolg-asgi", "--timeout=$timeout")
    Invoke-Checked "kubectl" @("-n", $Namespace, "rollout", "status", "deploy/dolg-worker", "--timeout=$timeout")
    Invoke-Checked "kubectl" @("-n", $Namespace, "rollout", "status", "deploy/dolg-nginx", "--timeout=$timeout")
}

Write-Host ""
Write-Host "Kubernetes objects:"
& kubectl -n $Namespace get pods,svc,pvc

Write-Host ""
Write-Host "DOLG Kubernetes stack is applied."
Write-Host "Open a local tunnel with:"
Write-Host "  kubectl -n $Namespace port-forward svc/dolg-nginx ${LocalPort}:80"

if ($PortForward) {
    Write-Host ""
    Write-Host "Starting foreground port-forward on http://localhost:$LocalPort/ ..."
    & kubectl -n $Namespace port-forward svc/dolg-nginx "${LocalPort}:80"
}
