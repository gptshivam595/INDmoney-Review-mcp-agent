# Quickstart

## 1. Local Setup

From the repository root:

```text
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
cd frontend
npm.cmd install
cd ..
```

Recommended helper commands on Windows PowerShell:

```text
.\start.ps1 setup
.\start.ps1 frontend-setup
```

If Windows blocks local scripts, run the same command through PowerShell's process-only bypass:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 setup
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 frontend-setup
```

Replace the command after `.\start.ps1` with any other helper command when needed.

Bash, Git Bash, WSL, Linux, or macOS:

```text
./start.sh setup
./start.sh frontend-setup
```

## 2. Environment

A local `.env` has already been prepared for this workspace.

If you need to recreate it, copy `.env.example` to `.env` and set:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_CLIENT_SECRET_FILE`
- `GOOGLE_TOKEN_PATH`
- `PULSE_CONFIRM_SEND=false`
- `PULSE_SCHEDULER_ENABLED=false`

## 3. Google Auth Bootstrap

Before live Docs and Gmail delivery, create a token:

```text
.\start.ps1 auth-google
```

That opens a local OAuth flow and writes `token.json` or the path in `GOOGLE_TOKEN_PATH`.

In Bash, use `./start.sh auth-google`.

## 4. Start the Backend

```text
.\start.ps1 server
```

Useful endpoints:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/api/overview`
- `http://127.0.0.1:8000/api/dashboard`
- `http://127.0.0.1:8000/api/runs`
- `http://127.0.0.1:8000/api/jobs`
- `http://127.0.0.1:8000/api/completion`

## 5. Start the Frontend

In a second terminal:

```text
.\start.ps1 frontend-dev
```

Then open:

```text
http://127.0.0.1:3000
```

The dashboard now auto-refreshes and shows:

- backend and delivery service health
- scheduler status and next-run forecast
- warnings and errors tracker
- product fleet health
- recent runs and delivery audit
- one-shot flow trigger controls

## 6. Run the Agent

From the CLI:

```text
.\start.ps1 run --product indmoney --draft-only
```

Use the same arguments with `./start.sh` in Bash.

Or from the dashboard:

- choose `INDMoney`
- leave draft mode enabled
- click `Run One-Shot Full Flow`

## 7. Current Completion Meaning

If `/api/completion` returns `partial`, that usually means the codebase is present but Google auth is still missing.

Once the token is available:

1. run INDMoney in draft mode first
2. confirm the Google Doc append succeeds
3. confirm the Gmail draft lands at `gptshivam595@gmail.com`
4. only then enable real send mode

## 8. Deployment Helpers

Deployment notes:

```text
.\deployment.ps1 check
.\deployment.ps1 railway
.\deployment.ps1 render
.\deployment.ps1 vercel
```

Use `./deployment.sh ...` in Bash.
