param(
    [switch]$Strict
)

$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$failures = 0
$warnings = 0

function Write-Result {
    param(
        [string]$Status,
        [string]$Name,
        [string]$Detail = ""
    )
    $line = "{0,-5} {1}" -f $Status, $Name
    if ($Detail) {
        $line = "$line - $Detail"
    }
    Write-Host $line
    if ($Status -eq "FAIL") {
        $script:failures += 1
    } elseif ($Status -eq "WARN") {
        $script:warnings += 1
    }
}

function Test-CommandExists {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Result "PASS" $Name $cmd.Source
        return $true
    }
    Write-Result "FAIL" $Name "not found in PATH"
    return $false
}

function Get-InstalledExtensionsFromDisk {
    $extensionRoot = Join-Path $env:USERPROFILE ".vscode\extensions"
    if (-not (Test-Path -LiteralPath $extensionRoot)) {
        return @()
    }

    $ids = New-Object System.Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $extensionRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $packagePath = Join-Path $_.FullName "package.json"
        if (-not (Test-Path -LiteralPath $packagePath)) {
            return
        }
        try {
            $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
            if ($package.publisher -and $package.name) {
                $ids.Add(("{0}.{1}" -f $package.publisher, $package.name).ToLowerInvariant())
            }
        }
        catch {
        }
    }
    return @($ids | Sort-Object -Unique)
}

function Invoke-WithTimeout {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 15,
        [string]$WorkingDirectory = $root
    )
    $argString = ($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + ($_ -replace '"', '\"') + '"'
        } else {
            $_
        }
    }) -join " "
    $stdoutPath = Join-Path $env:TEMP ("dolg-stack-out-{0}.txt" -f ([guid]::NewGuid()))
    $stderrPath = Join-Path $env:TEMP ("dolg-stack-err-{0}.txt" -f ([guid]::NewGuid()))
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $argString `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -NoNewWindow `
        -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F 2>$null | Out-Null
        } catch {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Remove-Item $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
        return @{
            TimedOut = $true
            ExitCode = $null
            Stdout = ""
            Stderr = "Timed out after $TimeoutSeconds seconds"
        }
    }
    $process.WaitForExit() | Out-Null
    $process.Refresh()
    $stdout = if (Test-Path $stdoutPath) { Get-Content $stdoutPath -Raw -ErrorAction SilentlyContinue } else { "" }
    $stderr = if (Test-Path $stderrPath) { Get-Content $stderrPath -Raw -ErrorAction SilentlyContinue } else { "" }
    Remove-Item $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
    $exitCode = $process.ExitCode
    if ($null -eq $exitCode -and -not $stderr) {
        $exitCode = 0
    }
    return @{
        TimedOut = $false
        ExitCode = $exitCode
        Stdout = ($stdout | Out-String).Trim()
        Stderr = ($stderr | Out-String).Trim()
    }
}

Write-Host "DOLG stack health check"
Write-Host "Root: $root"
Write-Host ""

foreach ($cmd in @("code", "git", "node", "docker", "kubectl")) {
    Test-CommandExists $cmd | Out-Null
}

$npmCmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
if ($npmCmd) {
    Write-Result "PASS" "npm.cmd" $npmCmd.Source
} else {
    Write-Result "WARN" "npm.cmd" "PowerShell npm.ps1 may be blocked; install Node/npm or use cmd /c npm"
}

Write-Host ""
Write-Host "VS Code extensions"
$installed = @()
$codeList = Invoke-WithTimeout -FilePath "cmd.exe" -Arguments @("/d", "/c", "code", "--list-extensions") -TimeoutSeconds 20
if ($codeList.ExitCode -eq 0) {
    $installed = $codeList.Stdout -split "`r?`n" | Where-Object { $_ } | ForEach-Object { $_.ToLowerInvariant() }
} elseif ($codeList.TimedOut) {
    Write-Result "WARN" "code --list-extensions" "timed out; falling back to %USERPROFILE%\.vscode\extensions"
    $installed = Get-InstalledExtensionsFromDisk
} else {
    Write-Result "WARN" "code --list-extensions" "$($codeList.Stderr); falling back to %USERPROFILE%\.vscode\extensions"
    $installed = Get-InstalledExtensionsFromDisk
}
$requiredExtensions = @(
    "batisteo.vscode-django",
    "charliermarsh.ruff",
    "editorconfig.editorconfig",
    "humao.rest-client",
    "mikestead.dotenv",
    "ms-azuretools.vscode-containers",
    "ms-azuretools.vscode-docker",
    "ms-kubernetes-tools.vscode-kubernetes-tools",
    "ms-playwright.playwright",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-vscode.powershell",
    "ms-vscode-remote.remote-containers",
    "ms-vscode-remote.remote-wsl",
    "mtxr.sqltools",
    "mtxr.sqltools-driver-sqlite",
    "qwtel.sqlite-viewer",
    "redhat.vscode-yaml",
    "tamasfe.even-better-toml",
    "wholroyd.jinja"
)
foreach ($extension in $requiredExtensions) {
    if ($installed -contains $extension.ToLowerInvariant()) {
        Write-Result "PASS" "extension:$extension"
    } else {
        Write-Result "FAIL" "extension:$extension" "missing"
    }
}

Write-Host ""
Write-Host "Python/Django"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Result "PASS" "venv python" $venvPython
    foreach ($check in @(
        @{ Name = "python"; Args = @("--version") },
        @{ Name = "django"; Args = @("-m", "django", "--version") },
        @{ Name = "pytest"; Args = @("-m", "pytest", "--version") },
        @{ Name = "ruff"; Args = @("-m", "ruff", "--version") }
    )) {
        $result = Invoke-WithTimeout -FilePath $venvPython -Arguments $check.Args -TimeoutSeconds 60
        if ($result.ExitCode -eq 0) {
            Write-Result "PASS" $check.Name $result.Stdout
        } else {
            Write-Result "FAIL" $check.Name $result.Stderr
        }
    }
} else {
    Write-Result "FAIL" "venv python" "missing .venv\Scripts\python.exe"
}

Write-Host ""
Write-Host "Frontend"
if (Test-Path (Join-Path $root "frontend\package.json")) {
    Write-Result "PASS" "frontend package.json"
    if (Test-Path (Join-Path $root "frontend\node_modules")) {
        Write-Result "PASS" "frontend node_modules"
    } else {
        Write-Result "WARN" "frontend node_modules" "run task Frontend: npm install"
    }
    if (Test-Path (Join-Path $root "frontend\package-lock.json")) {
        Write-Result "PASS" "frontend package-lock.json"
    } else {
        Write-Result "WARN" "frontend package-lock.json" "npm install did not produce lockfile"
    }
} else {
    Write-Result "WARN" "frontend package.json" "missing"
}

Write-Host ""
Write-Host "Docker"
$serviceNames = @("hns", "vmcompute", "LxssManager", "com.docker.service")
$services = Get-Service -Name $serviceNames -ErrorAction SilentlyContinue |
    Select-Object Name, Status, StartType
foreach ($serviceName in $serviceNames) {
    $service = $services | Where-Object { $_.Name -eq $serviceName }
    if ($service) {
        $status = "$($service.Status), startup=$($service.StartType)"
        if ($serviceName -eq "com.docker.service" -and $service.Status -ne "Running") {
            Write-Result "WARN" "service:$serviceName" "$status; run task Stacks: prepare Lxss Docker Kubernetes (admin)"
        } elseif ($serviceName -in @("LxssManager", "vmcompute", "hns") -and $service.Status -ne "Running") {
            Write-Result "FAIL" "service:$serviceName" "$status; run task Stacks: prepare Lxss Docker Kubernetes (admin)"
        } else {
            Write-Result "PASS" "service:$serviceName" $status
        }
    } else {
        Write-Result "FAIL" "service:$serviceName" "missing; run task Stacks: prepare Lxss Docker Kubernetes (admin)"
    }
}
$docker = Get-Command "docker" -ErrorAction SilentlyContinue
if ($docker) {
    $dockerTimedOut = $false
    $dockerInfo = Invoke-WithTimeout -FilePath $docker.Source -Arguments @("info", "--format", "{{.ServerVersion}}") -TimeoutSeconds 20
    if ($dockerInfo.ExitCode -eq 0 -and $dockerInfo.Stdout) {
        Write-Result "PASS" "docker daemon" "server $($dockerInfo.Stdout)"
    } elseif ($dockerInfo.TimedOut) {
        $dockerTimedOut = $true
        Write-Result "FAIL" "docker daemon" "CLI timed out; run VS Code task Stacks: prepare Lxss Docker Kubernetes (admin), restart Windows if requested, then open Docker Desktop."
    } else {
        Write-Result "FAIL" "docker daemon" $dockerInfo.Stderr
    }
    if ($dockerTimedOut) {
        Write-Result "WARN" "docker compose config" "skipped because docker CLI is timing out"
    } else {
        $oldEnv = @{
            SECRET_KEY = $env:SECRET_KEY
            POSTGRES_PASSWORD = $env:POSTGRES_PASSWORD
            GRAFANA_ADMIN_PASSWORD = $env:GRAFANA_ADMIN_PASSWORD
            EMAIL_BACKEND = $env:EMAIL_BACKEND
            METRICS_TOKEN = $env:METRICS_TOKEN
        }
        $env:SECRET_KEY = if ($env:SECRET_KEY) { $env:SECRET_KEY } else { "local-vscode-stack-check-secret-key-000000000000" }
        $env:POSTGRES_PASSWORD = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "local-postgres-password" }
        $env:GRAFANA_ADMIN_PASSWORD = if ($env:GRAFANA_ADMIN_PASSWORD) { $env:GRAFANA_ADMIN_PASSWORD } else { "local-grafana-password" }
        $env:EMAIL_BACKEND = if ($env:EMAIL_BACKEND) { $env:EMAIL_BACKEND } else { "django.core.mail.backends.locmem.EmailBackend" }
        $env:METRICS_TOKEN = if ($env:METRICS_TOKEN) { $env:METRICS_TOKEN } else { "local-metrics-token" }
        $compose = Invoke-WithTimeout -FilePath $docker.Source -Arguments @("compose", "--env-file", ".env", "-f", "deploy/docker-compose.yml", "config", "--quiet") -TimeoutSeconds 30
        foreach ($key in $oldEnv.Keys) {
            if ($null -eq $oldEnv[$key]) {
                Remove-Item "Env:$key" -ErrorAction SilentlyContinue
            } else {
                Set-Item "Env:$key" $oldEnv[$key]
            }
        }
        if ($compose.ExitCode -eq 0) {
            Write-Result "PASS" "docker compose config"
        } elseif ($compose.TimedOut) {
            Write-Result "FAIL" "docker compose config" "timed out"
        } else {
            Write-Result "WARN" "docker compose config" $compose.Stderr
        }
    }
}

Write-Host ""
Write-Host "Kubernetes"
$kubectl = Get-Command "kubectl" -ErrorAction SilentlyContinue
if ($kubectl) {
    $context = Invoke-WithTimeout -FilePath $kubectl.Source -Arguments @("config", "current-context") -TimeoutSeconds 10
    if ($context.ExitCode -eq 0 -and $context.Stdout) {
        Write-Result "PASS" "kubectl context" $context.Stdout
    } else {
        $kubeconfig = Join-Path $env:USERPROFILE ".kube\config"
        if (-not (Test-Path -LiteralPath $kubeconfig)) {
            Write-Result "FAIL" "kubectl context" "no current context and kubeconfig is missing at $kubeconfig; run task Stacks: prepare Lxss Docker Kubernetes (admin), then enable Docker Desktop Kubernetes."
        } else {
            Write-Result "FAIL" "kubectl context" "no current context in $kubeconfig; enable Docker Desktop Kubernetes or set kubeconfig."
        }
    }
    $kustomize = Invoke-WithTimeout -FilePath $kubectl.Source -Arguments @("kustomize", "deploy/k8s") -TimeoutSeconds 60
    if ($kustomize.ExitCode -eq 0 -and $kustomize.Stdout) {
        Write-Result "PASS" "kubectl kustomize" "rendered deploy/k8s"
    } elseif ($kustomize.TimedOut) {
        Write-Result "FAIL" "kubectl kustomize" "timed out"
    } else {
        Write-Result "FAIL" "kubectl kustomize" $kustomize.Stderr
    }
}

Write-Host ""
Write-Host "SQL"
if (Test-Path (Join-Path $root "db.sqlite3")) {
    Write-Result "PASS" "db.sqlite3"
} else {
    Write-Result "WARN" "db.sqlite3" "missing; run migrations"
}
if (Get-Command "sqlite3" -ErrorAction SilentlyContinue) {
    Write-Result "PASS" "sqlite3 CLI"
} else {
    Write-Result "WARN" "sqlite3 CLI" "missing; VS Code SQLTools/SQLite Viewer still work with db.sqlite3. Install SQLite CLI later if manage.py dbshell is needed."
}

Write-Host ""
Write-Host "Summary: failures=$failures warnings=$warnings"
if ($failures -gt 0 -or ($Strict -and $warnings -gt 0)) {
    exit 1
}
exit 0
