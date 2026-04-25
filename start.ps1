[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Command = "help",

  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { Join-Path $RootDir ".venv" }
$FrontendDir = if ($env:FRONTEND_DIR) { $env:FRONTEND_DIR } else { Join-Path $RootDir "frontend" }

function Get-SystemPython {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return $python.Source
  }

  $python3 = Get-Command python3 -ErrorAction SilentlyContinue
  if ($python3) {
    return $python3.Source
  }

  throw "Python 3.11+ is required but was not found in PATH."
}

function Get-Python {
  $venvPython = Join-Path $VenvDir "Scripts/python.exe"
  if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    return $venvPython
  }

  return Get-SystemPython
}

function Get-Npm {
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if ($npm) {
    return $npm.Source
  }

  $npm = Get-Command npm -ErrorAction SilentlyContinue
  if ($npm) {
    return $npm.Source
  }

  throw "npm is required but was not found in PATH."
}

function New-VenvIfMissing {
  if (-not (Test-Path -LiteralPath $VenvDir -PathType Container)) {
    $python = Get-SystemPython
    & $python -m venv $VenvDir
  }
}

function Install-BackendDependencies {
  New-VenvIfMissing
  $python = Get-Python
  & $python -m pip install --upgrade pip
  & $python -m pip install -e $RootDir
  & $python -m pip install -r (Join-Path $RootDir "requirements.txt")
}

function Install-FrontendDependencies {
  if (-not (Test-Path -LiteralPath $FrontendDir -PathType Container)) {
    throw "Frontend directory not found at $FrontendDir."
  }

  $npm = Get-Npm
  Push-Location $FrontendDir
  try {
    & $npm install
  }
  finally {
    Pop-Location
  }
}

function Import-DotEnv {
  $envPath = Join-Path $RootDir ".env"
  if (Test-Path -LiteralPath $envPath -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $envPath) {
      $trimmed = $line.Trim()
      if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
        continue
      }

      $key, $value = $trimmed.Split("=", 2)
      $key = $key.Trim()
      $value = $value.Trim().Trim('"').Trim("'")
      if ($key) {
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
      }
    }
  }

  if (-not $env:PULSE_DATABASE_PATH) {
    $env:PULSE_DATABASE_PATH = Join-Path $RootDir "data/pulse.db"
  }
  if (-not $env:PULSE_PRODUCTS_PATH) {
    $env:PULSE_PRODUCTS_PATH = Join-Path $RootDir "products.yaml"
  }
}

function Invoke-Pulse {
  Import-DotEnv
  $python = Get-Python
  & $python -m agent.__main__ @args
}

function Start-BackendServer {
  Import-DotEnv
  $port = if ($env:PORT) { $env:PORT } else { "8000" }
  Invoke-Pulse serve --host 0.0.0.0 --port $port
}

function Start-FrontendDev {
  Import-DotEnv
  $port = if ($env:PORT) { $env:PORT } else { "8000" }
  if (-not $env:NEXT_PUBLIC_API_BASE_URL) {
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$port"
  }

  $npm = Get-Npm
  Push-Location $FrontendDir
  try {
    & $npm run dev
  }
  finally {
    Pop-Location
  }
}

function Build-Frontend {
  Import-DotEnv
  $port = if ($env:PORT) { $env:PORT } else { "8000" }
  if (-not $env:NEXT_PUBLIC_API_BASE_URL) {
    $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$port"
  }

  $npm = Get-Npm
  Push-Location $FrontendDir
  try {
    & $npm run build
  }
  finally {
    Pop-Location
  }
}

function Show-Usage {
  @"
Usage: .\start.ps1 <command> [args]

Commands:
  setup                         Create .venv and install backend dependencies
  frontend-setup                Install frontend dependencies
  init-db                       Initialize the local SQLite database
  list-products                 List configured products
  plan-run --product <key>      Create or load a deterministic run
  ingest ...                    Run the ingestion phase
  analyze --run <run_id>        Run the analysis phase
  summarize --run <run_id>      Run the summarization phase
  render --run <run_id>         Run the rendering phase
  run-weekly [--week <iso>]     Run all active products for a week
  auth-google                   Launch local Google OAuth and save token.json
  pulse <args...>               Pass any command directly to the pulse CLI
  server                        Start the FastAPI operator API on PORT or 8000
  frontend-dev                  Start the Next.js dashboard locally
  frontend-build                Build the Next.js dashboard
  test                          Run pytest
  lint                          Run ruff and mypy
  help                          Show this message

Examples:
  .\start.ps1 setup
  .\start.ps1 frontend-setup
  .\start.ps1 init-db
  .\start.ps1 auth-google
  .\start.ps1 run --product indmoney --draft-only
  .\start.ps1 pulse plan-run --product indmoney --week 2026-W17
  .\start.ps1 server
  .\start.ps1 frontend-dev
"@
}

switch ($Command) {
  "setup" {
    Install-BackendDependencies
    "Environment ready in $VenvDir"
  }
  "frontend-setup" {
    Install-FrontendDependencies
    "Frontend dependencies installed in $FrontendDir"
  }
  { $_ -in @("init-db", "list-products", "plan-run", "ingest", "analyze", "summarize", "render", "publish-docs", "publish-gmail", "run", "run-weekly", "serve", "auth-google") } {
    Invoke-Pulse $Command @RemainingArgs
  }
  "pulse" {
    Invoke-Pulse @RemainingArgs
  }
  { $_ -in @("server", "mcp-server") } {
    Start-BackendServer
  }
  "frontend-dev" {
    Start-FrontendDev
  }
  "frontend-build" {
    Build-Frontend
  }
  "test" {
    $python = Get-Python
    & $python -m pytest @RemainingArgs
  }
  "lint" {
    $python = Get-Python
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) {
      exit $LASTEXITCODE
    }
    & $python -m mypy
  }
  { $_ -in @("help", "-h", "--help") } {
    Show-Usage
  }
  default {
    Write-Error "Unknown command: $Command`n`n$(Show-Usage)"
    exit 1
  }
}
