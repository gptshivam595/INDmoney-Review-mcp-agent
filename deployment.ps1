[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Show-Usage {
  @"
Usage: .\deployment.ps1 <target>

Targets:
  check       Verify deployment files exist
  railway     Show Railway backend deployment notes
  render      Show Render backend deployment notes
  vercel      Show Vercel frontend deployment notes
  all         Show the full recommended deployment order

Examples:
  .\deployment.ps1 check
  .\deployment.ps1 railway
  .\deployment.ps1 vercel
  .\deployment.ps1 all
"@
}

function Test-DeploymentFiles {
  $required = @(
    "README.md",
    "start.sh",
    "deployment.sh",
    "Dockerfile",
    "railway.json",
    "render.yaml",
    "frontend/vercel.json",
    "docs/deployment.md",
    "docs/quickstart.md"
  )

  $missing = @()
  foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $RootDir $path) -PathType Leaf)) {
      $missing += $path
    }
  }

  if ($missing.Count -gt 0) {
    foreach ($path in $missing) {
      Write-Error "Missing: $path"
    }
    exit 1
  }

  "Deployment files look present."
}

function Show-RailwayNotes {
  @"
Railway backend:
  1. Deploy from the repository root.
  2. Use the root Dockerfile.
  3. Attach a persistent volume at /app/data.
  4. Set:
     PULSE_DATABASE_PATH=/app/data/pulse.db
     PULSE_PRODUCTS_PATH=/app/products.yaml
     PULSE_API_CORS_ORIGINS=https://<your-vercel-domain>
     GOOGLE_CLIENT_ID=...
     GOOGLE_CLIENT_SECRET=...
     GOOGLE_TOKEN_PATH=/app/data/token.json
  5. Verify:
     /health
     /api/dashboard
"@
}

function Show-RenderNotes {
  @"
Render backend:
  1. Use render.yaml from the repository root.
  2. Confirm the persistent disk is mounted at /app/data.
  3. Add missing secrets in the Render dashboard:
     GOOGLE_CLIENT_ID
     GOOGLE_CLIENT_SECRET
     GOOGLE_MCP_TOKEN_JSON or a token file path
     PULSE_API_CORS_ORIGINS=https://<your-vercel-domain>
  4. Verify:
     /health
     /api/dashboard
"@
}

function Show-VercelNotes {
  @"
Vercel frontend:
  1. Import the repository into Vercel.
  2. Set Root Directory to frontend.
  3. frontend/vercel.json will be used automatically.
  4. Set:
     NEXT_PUBLIC_API_BASE_URL=https://<your-backend-domain>
  5. Deploy and open the dashboard.
"@
}

function Show-AllNotes {
  Show-RailwayNotes
  ""
  Show-VercelNotes
  ""
  @"
Recommended order:
  1. Deploy backend first.
  2. Deploy frontend second.
  3. Copy the final Vercel URL into backend CORS config.
  4. Add Google token auth.
  5. Trigger one draft-only INDMoney run from the dashboard.
"@
}

switch ($Target) {
  "check" { Test-DeploymentFiles }
  "railway" { Show-RailwayNotes }
  "render" { Show-RenderNotes }
  "vercel" { Show-VercelNotes }
  "all" { Show-AllNotes }
  { $_ -in @("help", "-h", "--help") } { Show-Usage }
  default {
    Write-Error "Unknown target: $Target`n`n$(Show-Usage)"
    exit 1
  }
}
