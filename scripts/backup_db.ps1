$ErrorActionPreference = "Stop"

$backupDir = Join-Path (Get-Location) "backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

if ($env:POSTGRES_DB) {
    $pgHost = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "localhost" }
    $pgPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5432" }
    $output = Join-Path $backupDir "dolg_postgres_$stamp.dump"
    pg_dump `
        --host=$pgHost `
        --port=$pgPort `
        --username=$env:POSTGRES_USER `
        --format=custom `
        --file=$output `
        $env:POSTGRES_DB
    Write-Host "PostgreSQL backup: $output"
} else {
    $source = Join-Path (Get-Location) "db.sqlite3"
    if (-not (Test-Path $source)) {
        throw "db.sqlite3 not found"
    }
    $output = Join-Path $backupDir "db_sqlite_$stamp.sqlite3"
    Copy-Item -LiteralPath $source -Destination $output
    Write-Host "SQLite backup: $output"
}
