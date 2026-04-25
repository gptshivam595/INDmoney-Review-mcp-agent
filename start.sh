#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT_DIR/frontend}"

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  echo "Python 3.11+ is required but was not found in PATH." >&2
  exit 1
}

pick_npm() {
  if command -v npm >/dev/null 2>&1; then
    command -v npm
    return
  fi
  if command -v npm.cmd >/dev/null 2>&1; then
    command -v npm.cmd
    return
  fi
  echo "npm is required but was not found in PATH." >&2
  exit 1
}

activate_venv() {
  if [[ -f "$VENV_DIR/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    return
  fi
  if [[ -f "$VENV_DIR/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/Scripts/activate"
    return
  fi
  echo "Virtual environment activation script not found in $VENV_DIR." >&2
  exit 1
}

ensure_venv() {
  local python_bin
  python_bin="$(pick_python)"
  if [[ ! -d "$VENV_DIR" ]]; then
    "$python_bin" -m venv "$VENV_DIR"
  fi
  activate_venv
}

install_dependencies() {
  ensure_venv
  python -m pip install --upgrade pip
  python -m pip install -e "$ROOT_DIR"
  python -m pip install -r "$ROOT_DIR/requirements.txt"
}

install_frontend_dependencies() {
  local npm_bin
  npm_bin="$(pick_npm)"
  if [[ ! -d "$FRONTEND_DIR" ]]; then
    echo "Frontend directory not found at $FRONTEND_DIR." >&2
    exit 1
  fi
  (cd "$FRONTEND_DIR" && "$npm_bin" install)
}

load_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ROOT_DIR/.env"
    set +a
  fi
  export PULSE_DATABASE_PATH="${PULSE_DATABASE_PATH:-$ROOT_DIR/data/pulse.db}"
  export PULSE_PRODUCTS_PATH="${PULSE_PRODUCTS_PATH:-$ROOT_DIR/products.yaml}"
}

run_pulse() {
  ensure_venv
  load_env
  python -m agent.__main__ "$@"
}

run_server() {
  local port="${PORT:-8000}"
  run_pulse serve --host 0.0.0.0 --port "$port"
}

run_frontend_dev() {
  local npm_bin
  npm_bin="$(pick_npm)"
  load_env
  export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:${PORT:-8000}}"
  (cd "$FRONTEND_DIR" && "$npm_bin" run dev)
}

run_frontend_build() {
  local npm_bin
  npm_bin="$(pick_npm)"
  load_env
  export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:${PORT:-8000}}"
  (cd "$FRONTEND_DIR" && "$npm_bin" run build)
}

usage() {
  cat <<'EOF'
Usage: ./start.sh <command> [args]

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
  ./start.sh setup
  ./start.sh frontend-setup
  ./start.sh init-db
  ./start.sh auth-google
  ./start.sh run --product indmoney --draft-only
  ./start.sh pulse plan-run --product indmoney --week 2026-W17
  ./start.sh server
  ./start.sh frontend-dev
EOF
}

main() {
  local command="${1:-help}"
  if [[ $# -gt 0 ]]; then
    shift
  fi

  case "$command" in
    setup)
      install_dependencies
      echo "Environment ready in $VENV_DIR"
      ;;
    frontend-setup)
      install_frontend_dependencies
      echo "Frontend dependencies installed in $FRONTEND_DIR"
      ;;
    init-db|list-products|plan-run|ingest|analyze|summarize|render|publish-docs|publish-gmail|run|run-weekly|serve|auth-google)
      run_pulse "$command" "$@"
      ;;
    pulse)
      run_pulse "$@"
      ;;
    server|mcp-server)
      run_server
      ;;
    frontend-dev)
      run_frontend_dev
      ;;
    frontend-build)
      run_frontend_build
      ;;
    test)
      ensure_venv
      python -m pytest "$@"
      ;;
    lint)
      ensure_venv
      python -m ruff check .
      python -m mypy
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      echo "Unknown command: $command" >&2
      echo >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
