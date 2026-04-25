# Deployment Guide

## 1. Target Topology

- Backend: Railway
- Frontend dashboard: Vercel
- Persistent backend data: Railway volume mounted at `/app/data`

The backend serves both:

- the operator API
- the Google helper endpoints used by the current repo runtime

## 2. Railway Backend

### 2.1 Service Setup

1. Create a Railway project from this repository.
2. Deploy from the repository root.
3. Use the root `Dockerfile`.

Optional config-as-code:

- `railway.json` is included for basic restart behavior

The container now starts with:

```text
pulse serve --host 0.0.0.0 --port 8000
```

Before deploying, verify the required config and docs are present:

```text
.\deployment.ps1 check
```

If Windows blocks local scripts:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\deployment.ps1 check
```

Replace `check` with `railway`, `render`, `vercel`, or `all` when needed.

Use `./deployment.sh check` from Bash, Linux, macOS, Git Bash, or WSL.

### 2.2 Persistent Storage

Attach a Railway volume at:

```text
/app/data
```

This stores:

- `pulse.db`
- raw review snapshots
- summaries and rendered artifacts
- delivery metadata
- optional token files if you place them under the mounted volume path

### 2.3 Railway Environment Variables

Minimum recommended backend environment:

```text
PULSE_DATABASE_PATH=/app/data/pulse.db
PULSE_PRODUCTS_PATH=/app/products.yaml
PULSE_TIMEZONE=Asia/Kolkata
PULSE_CONFIRM_SEND=false
PULSE_SCHEDULER_ENABLED=false
PULSE_SCHEDULER_DAY_OF_WEEK=0
PULSE_SCHEDULER_HOUR_24=9
PULSE_SCHEDULER_MINUTE=0
PULSE_API_CORS_ORIGINS=https://<your-vercel-domain>
GOOGLE_CLIENT_ID=<your-client-id>
GOOGLE_CLIENT_SECRET=<your-client-secret>
GOOGLE_TOKEN_PATH=/app/data/token.json
GOOGLE_MCP_PROFILE=shivam
```

Alternative token injection:

```text
GOOGLE_MCP_TOKEN_JSON={"type":"authorized_user", ...}
```

## 3. Vercel Frontend

### 3.1 Project Setup

1. Import the same repository into Vercel.
2. Set the Root Directory to `frontend`.
3. Keep framework detection as Next.js.

### 3.2 Frontend Environment Variable

Set:

```text
NEXT_PUBLIC_API_BASE_URL=https://<your-railway-domain>
```

## 4. Deploy Order

1. Deploy Railway backend.
2. Attach `/app/data` volume.
3. Set backend environment variables.
4. Verify `GET /health` and `GET /api/overview`.
5. Deploy the Vercel frontend from `frontend/`.
6. Copy the final Vercel URL back into Railway as `PULSE_API_CORS_ORIGINS`.
7. Add a valid Google token by file or `GOOGLE_MCP_TOKEN_JSON`.
8. Trigger one draft-only INDMoney run from the dashboard or CLI.

## 5. Google Auth for Deployment

The backend is live-ready only after an authorized token exists.

You can supply auth by:

- mounting a valid token file at the `GOOGLE_TOKEN_PATH`
- or setting `GOOGLE_MCP_TOKEN_JSON` in Railway

For local token generation before deployment, use:

```text
python -m agent.__main__ auth-google
```

That command writes an authorized user token to `GOOGLE_TOKEN_PATH` or `token.json`.

## 6. Current Deployment Caveat

This repository now has a complete backend API and frontend dashboard, but the active runtime still uses the repo's built-in Google helper server. If you later migrate to an external stdio MCP server package, update the deployment commands and environment variables to match that transport.

## 7. Scheduler Note

The dashboard shows scheduler cadence and next-run forecasting from the `PULSE_SCHEDULER_*` environment variables.

Recommended production setup:

- keep the scheduler metadata enabled in the app for visibility
- use Railway cron or another external scheduler to actually hit the one-shot backend trigger on schedule
