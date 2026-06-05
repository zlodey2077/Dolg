# Sets up the local stdio MCP servers for Claude Code (install + config + verify).
# Thin wrapper around setup_mcp.mjs — JSON editing is done in Node because
# Windows PowerShell 5.1's ConvertTo-Json truncates nested objects (default
# -Depth 2) and would corrupt the large ~/.claude.json.
#
# Usage:  scripts\setup_mcp.ps1
# After it finishes, restart Claude Code so it re-reads the config.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
node (Join-Path $here 'setup_mcp.mjs')
exit $LASTEXITCODE
