param(
    [string]$SettingsPath = "$env:APPDATA\Code\User\settings.json",
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

function Set-JsonProperty($Object, [string]$Name, $Value) {
    $existing = $Object.PSObject.Properties[$Name]
    if ($existing) {
        $existing.Value = $Value
    }
    else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

if (-not (Test-Path -LiteralPath $SettingsPath)) {
    $dir = Split-Path -Parent $SettingsPath
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
    '{}' | Set-Content -LiteralPath $SettingsPath -Encoding UTF8
}

$raw = Get-Content -LiteralPath $SettingsPath -Raw
if ([string]::IsNullOrWhiteSpace($raw)) {
    $raw = '{}'
}

$settings = $raw | ConvertFrom-Json

$changes = [ordered]@{
    "python.analysis.nodeArguments" = @("--max-old-space-size=768")
    "python.analysis.enableParallelIndexing" = $false
    "python.analysis.indexing.followSymlinkedFolders" = $false
    "containers.contexts.showInStatusBar" = $false
}

foreach ($entry in $changes.GetEnumerator()) {
    Set-JsonProperty $settings $entry.Key $entry.Value
}

$json = $settings | ConvertTo-Json -Depth 20

if (-not $Apply) {
    Write-Host "Dry run only. Re-run with -Apply to update:"
    Write-Host $SettingsPath
    $changes.GetEnumerator() | ForEach-Object { Write-Host "  $($_.Key) = $($_.Value)" }
    exit 0
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = "$SettingsPath.bak-$stamp"
Copy-Item -LiteralPath $SettingsPath -Destination $backup
[System.IO.File]::WriteAllText($SettingsPath, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

Write-Host "Updated $SettingsPath"
Write-Host "Backup: $backup"
