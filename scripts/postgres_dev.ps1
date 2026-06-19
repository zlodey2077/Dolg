param(
    [ValidateSet("up", "down", "status", "url", "config")]
    [string]$Action = "up",
    [switch]$WithPgAdmin,
    [switch]$RemoveVolumes
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot "deploy/docker-compose.postgres-dev.yml"
$EnvFile = Join-Path $RepoRoot "deploy/.env.postgres.local"
$EnvExample = Join-Path $RepoRoot "deploy/postgres-dev.env.example"

function New-Token([int]$Bytes = 24) {
    $data = [byte[]]::new($Bytes)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($data)
    }
    finally {
        $rng.Dispose()
    }
    return ([Convert]::ToBase64String($data)).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Read-EnvFile([string]$Path) {
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
        $parts = $line.Split("=", 2)
        $key = $parts[0].TrimStart([char]0xFEFF)
        $map[$key] = $parts[1]
    }
    return $map
}

function Write-TextNoBom([string]$Path, [string]$Value) {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $utf8NoBom)
}

Set-Location $RepoRoot

if (-not (Test-Path $EnvFile)) {
    $password = New-Token 24
    $pgadminPassword = New-Token 18
    if (Test-Path $EnvExample) {
        $content = Get-Content -Raw -Encoding UTF8 $EnvExample
        $content = $content.Replace("local-postgres-password", $password)
        $content = $content.Replace("local-pgadmin-password", $pgadminPassword)
        Write-TextNoBom $EnvFile $content
    }
    else {
        Write-TextNoBom $EnvFile @"
POSTGRES_DB=dolg
POSTGRES_USER=dolg
POSTGRES_PASSWORD=$password
POSTGRES_BIND=127.0.0.1
POSTGRES_PORT=5432
PGADMIN_EMAIL=admin@dolg.local
PGADMIN_PASSWORD=$pgadminPassword
PGADMIN_BIND=127.0.0.1
PGADMIN_PORT=5050
"@
    }
    Write-Host "Created $EnvFile"
}

$envMap = Read-EnvFile $EnvFile
$db = if ($envMap.POSTGRES_DB) { $envMap.POSTGRES_DB } else { "dolg" }
$user = if ($envMap.POSTGRES_USER) { $envMap.POSTGRES_USER } else { "dolg" }
$passwordValue = if ($envMap.POSTGRES_PASSWORD) { $envMap.POSTGRES_PASSWORD } else { "local-postgres-password" }
$hostValue = if ($envMap.POSTGRES_BIND) { $envMap.POSTGRES_BIND } else { "127.0.0.1" }
$portValue = if ($envMap.POSTGRES_PORT) { $envMap.POSTGRES_PORT } else { "5432" }
$databaseUrl = "postgresql://${user}:${passwordValue}@${hostValue}:${portValue}/${db}"

$compose = @("compose", "--env-file", "deploy/.env.postgres.local", "-f", "deploy/docker-compose.postgres-dev.yml")
if ($WithPgAdmin) {
    $compose += @("--profile", "tools")
}

switch ($Action) {
    "config" {
        & docker @($compose + @("config"))
    }
    "up" {
        & docker @($compose + @("up", "-d"))
        Write-Host ""
        Write-Host "Postgres dev is starting."
        Write-Host "DATABASE_URL=$databaseUrl"
        Write-Host "Run migrations with:"
        Write-Host ("`$env:DATABASE_URL=""{0}""; .\.venv\Scripts\python.exe manage.py migrate" -f $databaseUrl)
        if ($WithPgAdmin) {
            $pgPort = if ($envMap.PGADMIN_PORT) { $envMap.PGADMIN_PORT } else { "5050" }
            Write-Host "pgAdmin: http://127.0.0.1:$pgPort/"
        }
    }
    "down" {
        $args = @("down")
        if ($RemoveVolumes) { $args += "-v" }
        & docker @($compose + $args)
    }
    "status" {
        & docker @($compose + @("ps"))
    }
    "url" {
        Write-Host "DATABASE_URL=$databaseUrl"
    }
}
