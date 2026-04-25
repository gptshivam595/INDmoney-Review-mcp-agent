#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./deployment.sh <target>

Targets:
  check       Verify deployment files exist
  railway     Show Railway backend deployment notes
  render      Show Render backend deployment notes
  vercel      Show Vercel frontend deployment notes
  all         Show the full recommended deployment order

Examples:
  ./deployment.sh check
  ./deployment.sh railway
  ./deployment.sh vercel
  ./deployment.sh all
EOF
}

check_files() {
  local missing=0
  for path in "README.md" "start.sh" "deployment.sh" "Dockerfile" "railway.json" "render.yaml" "frontend/vercel.json" "docs/deployment.md" "docs/quickstart.md"; do
    if [[ ! -f "$ROOT_DIR/$path" ]]; then
      echo "Missing: $path" >&2
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    exit 1
  fi
  echo "Deployment files look present."
}

railway_notes() {
  cat <<'EOF'
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
EOF
}

render_notes() {
  cat <<'EOF'
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
EOF
}

vercel_notes() {
  cat <<'EOF'
Vercel frontend:
  1. Import the repository into Vercel.
  2. Set Root Directory to frontend.
  3. frontend/vercel.json will be used automatically.
  4. Set:
     NEXT_PUBLIC_API_BASE_URL=https://<your-backend-domain>
  5. Deploy and open the dashboard.
EOF
}

all_notes() {
  railway_notes
  echo
  vercel_notes
  echo
  cat <<'EOF'
Recommended order:
  1. Deploy backend first.
  2. Deploy frontend second.
  3. Copy the final Vercel URL into backend CORS config.
  4. Add Google token auth.
  5. Trigger one draft-only INDMoney run from the dashboard.
EOF
}

main() {
  local target="${1:-all}"
  case "$target" in
    check)
      check_files
      ;;
    railway)
      railway_notes
      ;;
    render)
      render_notes
      ;;
    vercel)
      vercel_notes
      ;;
    all)
      all_notes
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      echo "Unknown target: $target" >&2
      echo >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
