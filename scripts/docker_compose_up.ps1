param(
    [string]$EnvFile = "deploy/.env.docker.local",
    [switch]$NoBuild,
    [switch]$NoSmoke,
    [int]$HealthTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot "deploy/docker-compose.yml"
$EnvPath = Join-Path $RepoRoot $EnvFile

function New-Token([int]$Bytes = 32) {
    $data = [byte[]]::new($Bytes)
    [Security.Cryptography.RandomNumberGenerator]::Fill($data)
    return ([Convert]::ToBase64String($data)).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Test-DockerReady {
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

Set-Location $RepoRoot

if (-not (Test-Path $EnvPath)) {
    $secret = New-Token 48
    $postgresPassword = New-Token 24
    $grafanaPassword = New-Token 18
    $metricsToken = "local-metrics-token-change-me"
    @"
DEBUG=False
DJANGO_SETTINGS_MODULE=Dolg_PR.settings_prod
SECRET_KEY=$secret
POSTGRES_DB=dolg
POSTGRES_USER=dolg
POSTGRES_PASSWORD=$postgresPassword
ALLOWED_HOSTS=localhost,127.0.0.1,web,asgi
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1
EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend
DEFAULT_FROM_EMAIL=DOLG <noreply@dolg.local>
METRICS_TOKEN=$metricsToken
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
HTTP_BIND=127.0.0.1
HTTP_PORT=8080
PROMETHEUS_BIND=127.0.0.1
PROMETHEUS_PORT=9090
GRAFANA_BIND=127.0.0.1
GRAFANA_PORT=3000
DJANGO_SUPERUSER_USERNAME=
DJANGO_SUPERUSER_PASSWORD=
DJANGO_SUPERUSER_EMAIL=
"@ | Set-Content -Path $EnvPath -Encoding UTF8
    Write-Host "Created local Docker env: $EnvFile"
}

if (-not (Test-DockerReady)) {
    Write-Warning "Docker Engine is not ready. Running Docker Desktop bootstrap first."
    & (Join-Path $RepoRoot "scripts/bootstrap_docker_desktop.ps1") -TimeoutSeconds 180 -StartVisible
}

docker compose --env-file $EnvFile -f $ComposeFile config | Out-Null

$upArgs = @("compose", "--env-file", $EnvFile, "-f", $ComposeFile, "up", "-d")
if (-not $NoBuild) {
    $upArgs += "--build"
}
& docker @upArgs

if (-not $NoSmoke) {
    $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
    do {
        docker compose --env-file $EnvFile -f $ComposeFile exec -T web curl -fsS http://localhost:8000/healthz/ 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "DOLG is healthy."
            Write-Host "Web:        http://localhost:8080/"
            Write-Host "Prometheus: http://localhost:9090/"
            Write-Host "Grafana:    http://localhost:3000/  (admin password is in $EnvFile)"
            exit 0
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    docker compose --env-file $EnvFile -f $ComposeFile ps
    docker compose --env-file $EnvFile -f $ComposeFile logs --tail=120 web
    throw "DOLG did not pass /healthz within $HealthTimeoutSeconds seconds."
}

docker compose --env-file $EnvFile -f $ComposeFile ps
