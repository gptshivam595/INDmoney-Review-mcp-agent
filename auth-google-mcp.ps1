$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $root ".env"

if (-not (Test-Path $envFile)) {
    throw ".env not found at $envFile"
}

$wantedKeys = @(
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_MCP_PROFILE"
)

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
        return
    }
    $parts = $line -split "=", 2
    if ($parts.Length -ne 2) {
        return
    }
    $key = $parts[0].Trim()
    $value = $parts[1].Trim()
    if ($wantedKeys -contains $key) {
        Set-Item -Path ("Env:" + $key) -Value $value
    }
}

if (-not $env:GOOGLE_CLIENT_ID -or -not $env:GOOGLE_CLIENT_SECRET) {
    throw "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is missing after loading .env"
}

Write-Host "Starting Google Docs MCP auth for profile '$($env:GOOGLE_MCP_PROFILE)'..."
& npx.cmd -y @a-bonus/google-docs-mcp auth
