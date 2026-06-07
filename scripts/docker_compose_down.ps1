param(
    [string]$EnvFile = "deploy/.env.docker.local",
    [switch]$Volumes
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot "deploy/docker-compose.yml"
Set-Location $RepoRoot

$args = @("compose", "--env-file", $EnvFile, "-f", $ComposeFile, "down", "--remove-orphans")
if ($Volumes) {
    $args += "-v"
}

& docker @args
