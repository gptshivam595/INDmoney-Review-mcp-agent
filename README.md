# Weekly Product Review Pulse

This project is an AI agent that reads App Store and Google Play reviews, clusters and summarizes them into a weekly pulse, appends the report to Google Docs, drafts or sends the Gmail notification, and exposes an operator dashboard for live health and one-shot triggers.

## What's Included

- Python backend agent under [agent](agent/)
- FastAPI operator API and Google delivery helper
- Next.js operator dashboard under [frontend](frontend/)
- deployment configs for Railway, Render, and Vercel
- Bash and PowerShell helper scripts for local setup and deployment checks
- phase docs and runbook under [docs](docs/)

## Quick Start

PowerShell on Windows:

```powershell
.\start.ps1 setup
.\start.ps1 frontend-setup
.\start.ps1 auth-google
.\start.ps1 server
.\start.ps1 frontend-dev
.\start.ps1 run --product indmoney --draft-only
```

If script execution is disabled, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 setup
```

Replace `setup` with any other `start.ps1` command when using that form.

Bash, Git Bash, WSL, Linux, or macOS:

```bash
./start.sh setup
./start.sh frontend-setup
./start.sh auth-google
./start.sh server
./start.sh frontend-dev
./start.sh run --product indmoney --draft-only
```

The dashboard runs at `http://127.0.0.1:3000` and expects the backend at `http://127.0.0.1:8000` unless `NEXT_PUBLIC_API_BASE_URL` is set.

## Local Run Flow

1. Install backend dependencies with `.\start.ps1 setup` or `./start.sh setup`
2. Install frontend dependencies with `.\start.ps1 frontend-setup` or `./start.sh frontend-setup`
3. Create Google auth with `.\start.ps1 auth-google` or `./start.sh auth-google`
4. Start the backend with `.\start.ps1 server` or `./start.sh server`
5. Start the dashboard with `.\start.ps1 frontend-dev` or `./start.sh frontend-dev`
6. Open `http://127.0.0.1:3000`

## Dashboard

The dashboard shows:

- live backend and delivery service health
- scheduler cadence and next-run forecast
- warnings and errors tracker
- product fleet health
- recent runs, jobs, and delivery audit
- one-shot full-flow and weekly trigger controls

## Deployment

- Railway backend: see [docs/deployment.md](docs/deployment.md)
- Render backend: use [render.yaml](render.yaml)
- Vercel frontend: set root directory to `frontend`

Deployment helper checks:

```powershell
.\deployment.ps1 check
```

If script execution is disabled:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deployment.ps1 check
```

Replace `check` with `railway`, `render`, `vercel`, or `all` when needed.

```bash
./deployment.sh check
```

Docs:

- [docs/quickstart.md](docs/quickstart.md)
- [docs/deployment.md](docs/deployment.md)
- [docs/runbook.md](docs/runbook.md)
