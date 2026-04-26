import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from agent.config import load_product_catalog, load_runtime_settings
from agent.ingestion.csv_upload import parse_uploaded_csv_reviews
from agent.orchestrator import PipelineDependencies, run_active_product_schedule, run_product_pipeline
from agent.storage import (
    count_runs_by_status,
    initialize_database,
    list_delivery_events,
    list_runs,
    summarize_database_counts,
    sync_products,
)
from agent.time_utils import scheduler_summary

app = FastAPI()
DEFAULT_NOTIFICATION_EMAIL = "gptshivam595@gmail.com"
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
OPERATOR_PRODUCT_KEY = "indmoney"
JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pulse-job")
JOB_LOCK = Lock()
JOB_REGISTRY: dict[str, dict[str, object]] = {}
PROBE_LOCK = Lock()
PROBE_CACHE: dict[str, object] = {"captured_at": None, "payload": None}

HTTP_500_RESPONSE: dict[int | str, dict[str, Any]] = {
    500: {"description": "Internal server error"}
}

try:
    _runtime_settings = load_runtime_settings()
except Exception:
    _runtime_settings = None
else:
    allowed_origins = _runtime_settings.resolve_api_cors_origins()
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

# ================================
# Load Credentials (Local or Render ENV)
# ================================

def get_creds():
    try:
        google_token = os.getenv("GOOGLE_TOKEN") or os.getenv("GOOGLE_MCP_TOKEN_JSON")
        if google_token is not None:
            token_info = json.loads(google_token)
            return Credentials.from_authorized_user_info(token_info)

        token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
        return Credentials.from_authorized_user_file(token_path)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth Error: {str(e)}")


def get_docs_service(creds):
    return build("docs", "v1", credentials=creds)


def get_drive_service(creds):
    return build("drive", "v3", credentials=creds)


def get_gmail_service(creds):
    return build("gmail", "v1", credentials=creds)


# ================================
# Models
# ================================

class DocRequest(BaseModel):
    title: str
    content: str


class MailRequest(BaseModel):
    to: str
    subject: str
    body: str


class EnsureDocRequest(BaseModel):
    title: str


class DocsBlockRequest(BaseModel):
    kind: str
    text: str | None = None
    items: list[str] = Field(default_factory=list)
    level: int | None = None


class AppendSectionRequest(BaseModel):
    document_title: str
    section_anchor: str
    heading: str
    blocks: list[DocsBlockRequest] = Field(default_factory=list)


class GmailDraftRequest(BaseModel):
    subject: str
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    html_body: str
    text_body: str


class SendDraftRequest(BaseModel):
    draft_id: str


class TriggerRunRequest(BaseModel):
    product_key: str
    iso_week: str | None = None
    draft_only: bool = True
    force_gmail_delivery: bool = True


class TriggerWeeklyRequest(BaseModel):
    iso_week: str | None = None
    draft_only: bool = True


class SchedulerControlRequest(BaseModel):
    enabled: bool


def _build_recipient_header(primary_to: str) -> str:
    recipients: list[str] = []
    for candidate in [primary_to, DEFAULT_NOTIFICATION_EMAIL]:
        normalized = candidate.strip()
        if normalized and normalized not in recipients:
            recipients.append(normalized)
    return ", ".join(recipients)


# ================================
# Health Check
# ================================

@app.get("/", responses=HTTP_500_RESPONSE)
def home():
    return {"status": "MCP Server Running"}


# ================================
# Create Google Doc
# ================================

@app.post("/create-doc", responses=HTTP_500_RESPONSE)
def create_doc(data: DocRequest):
    try:
        creds = get_creds()

        service = get_docs_service(creds)

        # Create document
        doc = service.documents().create(body={"title": data.title}).execute()
        doc_id = doc.get("documentId")

        # Insert content
        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": data.content
                }
            }
        ]

        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests}
        ).execute()

        doc_url = f"https://docs.google.com/document/d/{doc_id}"

        return {
            "message": "Document created",
            "doc_url": doc_url
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/docs/ensure-document", responses=HTTP_500_RESPONSE)
def ensure_document(data: EnsureDocRequest):
    try:
        creds = get_creds()
        drive_service = get_drive_service(creds)
        existing = _find_document_by_title(drive_service, data.title)
        if existing is not None:
            document = _read_document(get_docs_service(creds), existing["id"])
            return {
                "created": False,
                "document_id": existing["id"],
                "title": existing["name"],
                "doc_url": _doc_url(existing["id"]),
                "text_content": document["text_content"],
                "heading_lookup": document["heading_lookup"],
            }

        docs_service = get_docs_service(creds)
        created = docs_service.documents().create(body={"title": data.title}).execute()
        document_id = created.get("documentId")
        if not document_id:
            raise HTTPException(status_code=500, detail="Document creation returned no document id")
        document = _read_document(docs_service, document_id)
        return {
            "created": True,
            "document_id": document_id,
            "title": data.title,
            "doc_url": _doc_url(document_id),
            "text_content": document["text_content"],
            "heading_lookup": document["heading_lookup"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/docs/{document_id}", responses=HTTP_500_RESPONSE)
def get_document(document_id: str):
    try:
        creds = get_creds()
        document = _read_document(get_docs_service(creds), document_id)
        return {
            "document_id": document_id,
            "title": document["title"],
            "doc_url": _doc_url(document_id),
            "text_content": document["text_content"],
            "heading_lookup": document["heading_lookup"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/docs/{document_id}/append-section", responses=HTTP_500_RESPONSE)
def append_section(document_id: str, data: AppendSectionRequest):
    try:
        creds = get_creds()
        service = get_docs_service(creds)
        document = service.documents().get(documentId=document_id).execute()
        end_index = document["body"]["content"][-1]["endIndex"] - 1
        service.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": end_index},
                            "text": _render_section_text(data),
                        }
                    }
                ]
            },
        ).execute()
        return {"status": "ok", "document_id": document_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================
# Send Gmail
# ================================

@app.post("/send-mail", responses=HTTP_500_RESPONSE)
def send_mail(data: MailRequest):
    try:
        creds = get_creds()

        service = get_gmail_service(creds)
        recipient_header = _build_recipient_header(data.to)

        message = f"""To: {recipient_header}
Subject: {data.subject}

{data.body}
"""

        encoded_message = base64.urlsafe_b64encode(message.encode("utf-8")).decode("utf-8")

        create_message = {
            "raw": encoded_message
        }

        send_message = service.users().messages().send(
            userId="me",
            body=create_message
        ).execute()

        return {
            "message": "Email sent",
            "id": send_message["id"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gmail/search", responses=HTTP_500_RESPONSE)
def gmail_search(query: str):
    try:
        creds = get_creds()
        service = get_gmail_service(creds)
        messages_response = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=10,
        ).execute()
        drafts_response = service.users().drafts().list(userId="me", maxResults=100).execute()
        draft_lookup = {
            draft["message"]["id"]: draft["id"]
            for draft in drafts_response.get("drafts", [])
            if "message" in draft and "id" in draft["message"]
        }
        matches: list[dict[str, object]] = []
        for message_ref in messages_response.get("messages", []):
            message_id = message_ref["id"]
            message = service.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject"],
            ).execute()
            headers = message.get("payload", {}).get("headers", [])
            subject = next(
                (header.get("value", "") for header in headers if header.get("name") == "Subject"),
                "",
            )
            matches.append(
                {
                    "message_id": message_id,
                    "draft_id": draft_lookup.get(message_id),
                    "label_ids": message.get("labelIds", []),
                    "subject": subject,
                }
            )
        return {"matches": matches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/create-draft", responses=HTTP_500_RESPONSE)
def gmail_create_draft(data: GmailDraftRequest):
    try:
        creds = get_creds()
        service = get_gmail_service(creds)
        mime_message = _build_gmail_message(data)
        encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("utf-8")
        created = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": encoded_message}},
        ).execute()
        return {
            "draft_id": created["id"],
            "message_id": created["message"]["id"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gmail/send-draft", responses=HTTP_500_RESPONSE)
def gmail_send_draft(data: SendDraftRequest):
    try:
        creds = get_creds()
        service = get_gmail_service(creds)
        sent = service.users().drafts().send(
            userId="me",
            body={"id": data.draft_id},
        ).execute()
        return {"message_id": sent["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", responses=HTTP_500_RESPONSE)
def health():
    settings, catalog, database_path = _load_runtime_context()
    return {
        "status": "ok",
        "database_path": str(database_path),
        "products": len(catalog.products),
        "docs_mcp_base_url": settings.docs_mcp_base_url,
        "gmail_mcp_base_url": settings.gmail_mcp_base_url,
        "google_auth": _google_auth_status(),
    }


@app.get("/api/overview", responses=HTTP_500_RESPONSE)
def api_overview():
    settings, catalog, database_path = _load_runtime_context()
    filtered_runs = list_runs(database_path, limit=12, product_key=OPERATOR_PRODUCT_KEY)
    counts = summarize_database_counts(database_path)
    recent_delivery_events = [
        event
        for event in list_delivery_events(database_path, limit=20)
        if _delivery_event_matches_product(event, filtered_runs)
    ][:8]
    scheduler = scheduler_summary(
        enabled=settings.scheduler_enabled,
        timezone_name=settings.timezone,
        day_of_week=settings.scheduler_day_of_week,
        hour_24=settings.scheduler_hour_24,
        minute=settings.scheduler_minute,
    )
    scheduler["target_product_key"] = OPERATOR_PRODUCT_KEY
    mcp_checks = _workspace_probe_snapshot()
    services = _service_health_snapshot(
        settings=settings,
        database_path=database_path,
        recent_runs=filtered_runs,
        mcp_checks=mcp_checks,
    )
    issues = _issue_tracker(
        settings=settings,
        recent_runs=filtered_runs,
        recent_delivery_events=recent_delivery_events,
        services=services,
        mcp_checks=mcp_checks,
    )
    fleet = _fleet_health_snapshot(
        catalog=catalog,
        recent_runs=filtered_runs,
    )
    indmoney_product = catalog.get_product(OPERATOR_PRODUCT_KEY)
    return {
        "service": {
            "status": "ok",
            "database_path": str(database_path),
            "products_path": str(settings.resolve_products_path()),
            "confirm_send": settings.confirm_send,
        },
        "google_auth": _google_auth_status(),
        "scheduler": scheduler,
        "mcp_checks": mcp_checks,
        "services": services,
        "issues": issues,
        "fleet": fleet,
        "counts": counts,
        "runs_by_status": count_runs_by_status(database_path),
        "products": [
            {
                "product_key": indmoney_product.product_key,
                "display_name": indmoney_product.display_name,
                "active": indmoney_product.active,
                "stakeholders": indmoney_product.stakeholders.model_dump(mode="json"),
            }
        ],
        "recent_runs": [entry.model_dump(mode="json") for entry in filtered_runs[:8]],
        "recent_delivery_events": [entry.model_dump(mode="json") for entry in recent_delivery_events],
        "jobs": _list_jobs(),
    }


@app.get("/api/dashboard", responses=HTTP_500_RESPONSE)
def api_dashboard():
    return api_overview()


@app.get("/api/runs", responses=HTTP_500_RESPONSE)
def api_runs(limit: int = 20, product_key: str | None = None):
    _settings, _catalog, database_path = _load_runtime_context()
    safe_limit = max(1, min(limit, 100))
    return {
        "runs": [
            entry.model_dump(mode="json")
            for entry in list_runs(
                database_path,
                limit=safe_limit,
                product_key=product_key,
            )
        ]
    }


@app.get("/api/jobs", responses=HTTP_500_RESPONSE)
def api_jobs():
    return {"jobs": _list_jobs()}


@app.get("/api/scheduler", responses=HTTP_500_RESPONSE)
def api_scheduler():
    settings, _catalog, _database_path = _load_runtime_context()
    summary = scheduler_summary(
        enabled=settings.scheduler_enabled,
        timezone_name=settings.timezone,
        day_of_week=settings.scheduler_day_of_week,
        hour_24=settings.scheduler_hour_24,
        minute=settings.scheduler_minute,
    )
    summary["target_product_key"] = OPERATOR_PRODUCT_KEY
    return summary


@app.post("/api/scheduler", responses=HTTP_500_RESPONSE)
def api_update_scheduler(data: SchedulerControlRequest):
    settings, _catalog, database_path = _load_runtime_context()
    _write_scheduler_override(database_path, enabled=data.enabled)
    summary = scheduler_summary(
        enabled=data.enabled,
        timezone_name=settings.timezone,
        day_of_week=settings.scheduler_day_of_week,
        hour_24=settings.scheduler_hour_24,
        minute=settings.scheduler_minute,
    )
    summary["target_product_key"] = OPERATOR_PRODUCT_KEY
    return summary


@app.get("/api/completion", responses=HTTP_500_RESPONSE)
def api_completion():
    auth = _google_auth_status()
    frontend_exists = (Path.cwd() / "frontend").exists()
    phases = [
        {
            "phase": "phase-0-foundations",
            "status": "complete",
            "evidence": "CLI, config, storage, and tests are present.",
        },
        {
            "phase": "phase-1-ingestion",
            "status": "complete",
            "evidence": "App Store and Play Store ingestion modules and tests are present.",
        },
        {
            "phase": "phase-2-analysis",
            "status": "complete",
            "evidence": "Embeddings, clustering, and persisted analysis artifacts are implemented.",
        },
        {
            "phase": "phase-3-summarization",
            "status": "complete",
            "evidence": "Summarization, quote validation, and report persistence are implemented.",
        },
        {
            "phase": "phase-4-render",
            "status": "complete",
            "evidence": "Docs and Gmail render artifacts are produced locally.",
        },
        {
            "phase": "phase-5-docs-mcp",
            "status": "ready" if auth["token_available"] else "blocked",
            "evidence": (
                "Docs publish code is implemented. Live completion is blocked until "
                "Google auth token is available."
            ),
        },
        {
            "phase": "phase-6-gmail-mcp",
            "status": "ready" if auth["token_available"] else "blocked",
            "evidence": (
                "Gmail publish code is implemented. Live completion is blocked until "
                "Google auth token is available."
            ),
        },
        {
            "phase": "phase-7-orchestration",
            "status": "complete" if frontend_exists else "partial",
            "evidence": (
                "Checkpoint-aware orchestration exists, and the operator dashboard is "
                "present."
                if frontend_exists
                else "Orchestration is present, but the frontend dashboard is not yet in place."
            ),
        },
    ]
    overall_status = "complete" if auth["token_available"] and frontend_exists else "partial"
    return {
        "audit_date": datetime.now(UTC).date().isoformat(),
        "overall_status": overall_status,
        "google_auth": auth,
        "phases": phases,
    }


@app.post("/api/trigger/run", responses=HTTP_500_RESPONSE)
def api_trigger_run(data: TriggerRunRequest):
    settings, catalog, _database_path = _load_runtime_context()
    catalog.get_product(OPERATOR_PRODUCT_KEY)

    job_id = _create_job(
        kind="single-run",
        product_key=OPERATOR_PRODUCT_KEY,
        iso_week=data.iso_week,
        draft_only=data.draft_only,
    )
    JOB_EXECUTOR.submit(
        _execute_single_run_job,
        job_id,
        settings.model_copy(deep=True),
        catalog.model_copy(deep=True),
        data.model_dump(mode="json"),
    )
    return {"job": _get_job(job_id)}


@app.post("/api/trigger/upload-csv", responses=HTTP_500_RESPONSE)
async def api_trigger_csv_run(
    request: Request,
    product_key: str = OPERATOR_PRODUCT_KEY,
    iso_week: str | None = None,
    draft_only: bool = False,
):
    settings, catalog, _database_path = _load_runtime_context()
    if product_key != OPERATOR_PRODUCT_KEY:
        raise HTTPException(status_code=400, detail="Only INDMoney CSV uploads are supported.")
    catalog.get_product(OPERATOR_PRODUCT_KEY)

    csv_bytes = await request.body()
    if not csv_bytes:
        raise HTTPException(status_code=400, detail="CSV upload is empty.")
    if len(csv_bytes) > 2_000_000:
        raise HTTPException(status_code=413, detail="CSV upload is too large. Limit is 2 MB.")
    try:
        csv_text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV upload must be UTF-8 encoded.") from exc

    try:
        parsed_preview = parse_uploaded_csv_reviews(
            csv_text=csv_text,
            product_key=OPERATOR_PRODUCT_KEY,
            upload_id="validation",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = _create_job(
        kind="csv-upload-run",
        product_key=OPERATOR_PRODUCT_KEY,
        iso_week=iso_week,
        draft_only=draft_only,
    )
    _update_job(job_id, uploaded_rows=len(parsed_preview))
    JOB_EXECUTOR.submit(
        _execute_csv_upload_job,
        job_id,
        settings.model_copy(deep=True),
        catalog.model_copy(deep=True),
        {
            "csv_text": csv_text,
            "iso_week": iso_week,
            "draft_only": draft_only,
        },
    )
    return {"job": _get_job(job_id)}


@app.post("/api/trigger/weekly", responses=HTTP_500_RESPONSE)
def api_trigger_weekly(data: TriggerWeeklyRequest):
    settings, catalog, _database_path = _load_runtime_context()
    job_id = _create_job(
        kind="periodic-scheduler-run",
        product_key=OPERATOR_PRODUCT_KEY,
        iso_week=data.iso_week,
        draft_only=data.draft_only,
    )
    JOB_EXECUTOR.submit(
        _execute_weekly_job,
        job_id,
        settings.model_copy(deep=True),
        catalog.model_copy(deep=True),
        data.model_dump(mode="json"),
    )
    return {"job": _get_job(job_id)}


def _doc_url(document_id: str) -> str:
    return f"https://docs.google.com/document/d/{document_id}"


def _load_runtime_context():
    settings = load_runtime_settings()
    catalog = load_product_catalog(settings.resolve_products_path())
    database_path = settings.resolve_database_path()
    initialize_database(database_path)
    sync_products(database_path, catalog)
    scheduler_override = _read_scheduler_override(database_path)
    if scheduler_override is not None:
        settings = settings.model_copy(update={"scheduler_enabled": scheduler_override["enabled"]})
    return settings, catalog, database_path


def _google_auth_status() -> dict[str, object]:
    token_from_env = bool(os.getenv("GOOGLE_TOKEN") or os.getenv("GOOGLE_MCP_TOKEN_JSON"))
    token_path = Path(os.getenv("GOOGLE_TOKEN_PATH", "token.json"))
    token_file_exists = token_path.exists()
    client_secret_file = os.getenv("GOOGLE_CLIENT_SECRET_FILE")
    client_secret_file_exists = bool(client_secret_file and Path(client_secret_file).exists())
    return {
        "token_available": token_from_env or token_file_exists,
        "token_source": "env" if token_from_env else ("file" if token_file_exists else "missing"),
        "token_path": str(token_path),
        "client_id_present": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "client_secret_present": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
        "client_secret_file_exists": client_secret_file_exists,
        "profile": os.getenv("GOOGLE_MCP_PROFILE", "default"),
    }


def _service_health_snapshot(
    *,
    settings,
    database_path: Path,
    recent_runs,
    mcp_checks,
) -> list[dict[str, object]]:
    auth = _google_auth_status()
    recent_failures = [run for run in recent_runs if run.status == "failed"]
    active_jobs = [job for job in _list_jobs() if str(job.get("status")) in {"queued", "running"}]
    services = [
        {
            "key": "backend-api",
            "label": "Backend API",
            "status": "active",
            "detail": "Operator API is responding.",
        },
        {
            "key": "database",
            "label": "SQLite Database",
            "status": "active" if database_path.exists() else "warning",
            "detail": str(database_path),
        },
        {
            "key": "docs-delivery",
            "label": "Docs Delivery",
            "status": str(mcp_checks["docs"]["status"]),
            "detail": str(mcp_checks["docs"]["detail"]),
        },
        {
            "key": "gmail-delivery",
            "label": "Gmail Delivery",
            "status": str(mcp_checks["gmail"]["status"]),
            "detail": str(mcp_checks["gmail"]["detail"]),
        },
        {
            "key": "scheduler",
            "label": "Scheduler",
            "status": "active" if settings.scheduler_enabled else "inactive",
            "detail": (
                f"Recurring cadence is configured for {OPERATOR_PRODUCT_KEY}."
                if settings.scheduler_enabled
                else f"Recurring scheduler is disabled for {OPERATOR_PRODUCT_KEY}; use one-shot triggers."
            ),
        },
        {
            "key": "worker-pool",
            "label": "Background Workers",
            "status": "active" if len(active_jobs) < 2 else "warning",
            "detail": f"{len(active_jobs)} active job(s) in the queue.",
        },
        {
            "key": "run-health",
            "label": "Recent Run Health",
            "status": "error" if recent_failures else "active",
            "detail": (
                f"{len(recent_failures)} recent failed run(s) detected."
                if recent_failures
                else "No recent failed runs recorded."
            ),
        },
    ]
    return services


def _issue_tracker(
    *,
    settings,
    recent_runs,
    recent_delivery_events,
    services,
    mcp_checks,
) -> dict[str, list[dict[str, object]]]:
    warnings: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    auth = _google_auth_status()

    if not auth["token_available"]:
        warnings.append(
            {
                "code": "missing_google_token",
                "title": "Google token missing",
                "detail": "Docs and Gmail live delivery are blocked until token.json or GOOGLE_MCP_TOKEN_JSON is available.",
            }
        )
    if not settings.confirm_send:
        warnings.append(
            {
                "code": "draft_mode_only",
                "title": "Gmail send is gated",
                "detail": "PULSE_CONFIRM_SEND is false, so the system stays in draft-safe mode.",
            }
        )
    if not settings.scheduler_enabled:
        warnings.append(
            {
                "code": "scheduler_disabled",
                "title": "Scheduler disabled",
                "detail": "Recurring INDMoney runs are off; operators must trigger flows manually or use Railway cron.",
            }
        )

    for key in ("docs", "gmail"):
        probe = mcp_checks[key]
        if probe["status"] == "error":
            errors.append(
                {
                    "code": f"{key}_mcp_error",
                    "title": f"{str(probe['label'])} error",
                    "detail": str(probe["detail"]),
                }
            )
        elif probe["status"] == "warning":
            warnings.append(
                {
                    "code": f"{key}_mcp_warning",
                    "title": f"{str(probe['label'])} needs attention",
                    "detail": str(probe["detail"]),
                }
            )

    failure_runs = [run for run in recent_runs if run.status == "failed"]
    for run in failure_runs[:5]:
        detail = run.error_message or "The run ended in failed state."
        errors.append(
            {
                "code": "run_failed",
                "title": f"Run failed for {run.product_key} {run.iso_week}",
                "detail": detail,
                "run_id": run.run_id,
            }
        )
        lowered = detail.lower()
        if any(term in lowered for term in ["docs", "gmail", "google", "mcp", "oauth", "auth"]):
            errors.append(
                {
                    "code": "workspace_delivery_failure",
                    "title": "Google Docs or Gmail delivery failure detected",
                    "detail": detail,
                    "run_id": run.run_id,
                }
            )

    if not recent_delivery_events:
        warnings.append(
            {
                "code": "no_deliveries",
                "title": "No delivery events recorded",
                "detail": "The pipeline has not yet recorded a Docs or Gmail delivery in this environment.",
            }
        )

    unhealthy_services = [service for service in services if service["status"] in {"warning", "error"}]
    if unhealthy_services and not errors:
        warnings.append(
            {
                "code": "service_attention",
                "title": "One or more services need attention",
                "detail": ", ".join(str(service["label"]) for service in unhealthy_services),
            }
        )

    return {"warnings": warnings, "errors": errors}


def _fleet_health_snapshot(*, catalog, recent_runs) -> list[dict[str, object]]:
    latest_by_product: dict[str, object] = {}
    for run in recent_runs:
        latest_by_product.setdefault(run.product_key, run)

    fleet: list[dict[str, object]] = []
    for product in catalog.products:
        if product.product_key != OPERATOR_PRODUCT_KEY:
            continue
        latest = latest_by_product.get(product.product_key)
        status = "idle"
        detail = "No run recorded yet in this environment."
        last_run_id = None
        last_started_at = None
        if latest is not None:
            status = latest.status
            detail = latest.error_message or (
                latest.gmail_message_id
                or latest.gmail_draft_id
                or latest.gdoc_deep_link
                or "Run present with no delivery metadata yet."
            )
            last_run_id = latest.run_id
            last_started_at = latest.started_at

        fleet.append(
            {
                "product_key": product.product_key,
                "display_name": product.display_name,
                "active": product.active,
                "latest_status": status,
                "latest_detail": detail,
                "latest_run_id": last_run_id,
                "latest_started_at": last_started_at,
                "stakeholder_count": len(product.stakeholders.to)
                + len(product.stakeholders.cc)
                + len(product.stakeholders.bcc),
            }
        )
    return fleet


def _create_job(
    *,
    kind: str,
    product_key: str | None,
    iso_week: str | None,
    draft_only: bool,
) -> str:
    job_id = uuid4().hex
    with JOB_LOCK:
        JOB_REGISTRY[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "status": "queued",
            "product_key": product_key,
            "iso_week": iso_week,
            "draft_only": draft_only,
            "created_at": _utc_now_text(),
            "started_at": None,
            "finished_at": None,
            "run_ids": [],
            "error_message": None,
        }
    return job_id


def _update_job(job_id: str, **updates: object) -> None:
    with JOB_LOCK:
        existing = JOB_REGISTRY.get(job_id)
        if existing is None:
            return
        existing.update(updates)


def _get_job(job_id: str) -> dict[str, object]:
    with JOB_LOCK:
        existing = JOB_REGISTRY.get(job_id)
        if existing is None:
            msg = f"Unknown job id: {job_id}"
            raise HTTPException(status_code=404, detail=msg)
        return dict(existing)


def _list_jobs() -> list[dict[str, object]]:
    with JOB_LOCK:
        jobs = [
            dict(job)
            for job in JOB_REGISTRY.values()
            if job.get("product_key") in {None, OPERATOR_PRODUCT_KEY}
        ]
    return sorted(jobs, key=lambda item: str(item["created_at"]), reverse=True)


def _execute_single_run_job(
    job_id: str,
    settings,
    catalog,
    payload: dict[str, object],
) -> None:
    _update_job(job_id, status="running", started_at=_utc_now_text())
    try:
        result = run_product_pipeline(
            settings=settings,
            catalog=catalog,
            product_key=OPERATOR_PRODUCT_KEY,
            iso_week=payload.get("iso_week"),
            draft_only=bool(payload.get("draft_only", True)),
            force_gmail_delivery=bool(payload.get("force_gmail_delivery", True)),
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            finished_at=_utc_now_text(),
            error_message=str(exc),
        )
        return
    _update_job(
        job_id,
        status="completed",
        finished_at=_utc_now_text(),
        run_ids=[result.run_id],
    )


def _execute_csv_upload_job(
    job_id: str,
    settings,
    catalog,
    payload: dict[str, object],
) -> None:
    _update_job(job_id, status="running", started_at=_utc_now_text())
    csv_text = str(payload.get("csv_text", ""))

    def csv_fetcher(product, _since_date):
        return parse_uploaded_csv_reviews(
            csv_text=csv_text,
            product_key=product.product_key,
            upload_id=job_id,
        )

    def empty_fetcher(_product, _since_date):
        return []

    try:
        result = run_product_pipeline(
            settings=settings,
            catalog=catalog,
            product_key=OPERATOR_PRODUCT_KEY,
            iso_week=payload.get("iso_week"),
            run_key_suffix=f"csv-{job_id[:8]}",
            draft_only=bool(payload.get("draft_only", False)),
            force_gmail_delivery=True,
            dependencies=PipelineDependencies(
                appstore_fetcher=csv_fetcher,
                playstore_fetcher=empty_fetcher,
            ),
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            finished_at=_utc_now_text(),
            error_message=str(exc),
        )
        return
    _update_job(
        job_id,
        status="completed",
        finished_at=_utc_now_text(),
        run_ids=[result.run_id],
    )


def _execute_weekly_job(
    job_id: str,
    settings,
    catalog,
    payload: dict[str, object],
) -> None:
    _update_job(job_id, status="running", started_at=_utc_now_text())
    try:
        result = run_product_pipeline(
            settings=settings,
            catalog=catalog,
            product_key=OPERATOR_PRODUCT_KEY,
            iso_week=payload.get("iso_week"),
            draft_only=bool(payload.get("draft_only", True)),
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            finished_at=_utc_now_text(),
            error_message=str(exc),
        )
        return
    _update_job(
        job_id,
        status="completed",
        finished_at=_utc_now_text(),
        run_ids=[result.run_id],
    )


def _utc_now_text() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _find_document_by_title(drive_service, title: str):
    escaped_title = title.replace("'", "\\'")
    response = drive_service.files().list(
        q=(
            f"mimeType='{GOOGLE_DOC_MIME_TYPE}' and trashed=false "
            f"and name='{escaped_title}'"
        ),
        fields="files(id, name)",
        orderBy="createdTime desc",
        pageSize=2,
        spaces="drive",
    ).execute()
    files = response.get("files", [])
    if not files:
        return None
    return files[0]


def _read_document(service, document_id: str) -> dict[str, object]:
    document = service.documents().get(documentId=document_id).execute()
    heading_lookup: dict[str, str] = {}
    text_fragments: list[str] = []
    for element in document.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if paragraph is None:
            continue
        paragraph_text = _paragraph_text(paragraph)
        if paragraph_text:
            text_fragments.append(paragraph_text)
        named_style = paragraph.get("paragraphStyle", {}).get("namedStyleType", "")
        if named_style.startswith("HEADING") and paragraph_text:
            heading_lookup.setdefault(paragraph_text, "")
    return {
        "title": document.get("title", ""),
        "text_content": "\n".join(text_fragments),
        "heading_lookup": heading_lookup,
    }


def _paragraph_text(paragraph: dict[str, object]) -> str:
    parts: list[str] = []
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun", {})
        content = text_run.get("content", "")
        if isinstance(content, str):
            parts.append(content)
    return "".join(parts).strip()


def _render_section_text(data: AppendSectionRequest) -> str:
    lines: list[str] = [""]
    for block in data.blocks:
        if block.kind == "bullet_list":
            lines.extend(f"- {item}" for item in block.items)
            lines.append("")
            continue
        if block.text:
            lines.append(block.text)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_gmail_message(data: GmailDraftRequest) -> EmailMessage:
    message = EmailMessage()
    to_header = _build_recipient_header(", ".join(data.to))
    if to_header:
        message["To"] = to_header
    if data.cc:
        message["Cc"] = ", ".join(data.cc)
    if data.bcc:
        message["Bcc"] = ", ".join(data.bcc)
    message["Subject"] = data.subject
    message.set_content(data.text_body)
    message.add_alternative(data.html_body, subtype="html")
    return message


def _scheduler_override_path(database_path: Path) -> Path:
    return database_path.parent / "scheduler-state.json"


def _read_scheduler_override(database_path: Path) -> dict[str, bool] | None:
    override_path = _scheduler_override_path(database_path)
    if not override_path.exists():
        return None
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return None
    return {"enabled": enabled}


def _write_scheduler_override(database_path: Path, *, enabled: bool) -> None:
    override_path = _scheduler_override_path(database_path)
    override_path.parent.mkdir(parents=True, exist_ok=True)
    override_path.write_text(
        json.dumps(
            {
                "enabled": enabled,
                "product_key": OPERATOR_PRODUCT_KEY,
                "updated_at": _utc_now_text(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _workspace_probe_snapshot() -> dict[str, dict[str, object]]:
    with PROBE_LOCK:
        captured_at = PROBE_CACHE.get("captured_at")
        cached_payload = PROBE_CACHE.get("payload")
        if isinstance(captured_at, datetime) and isinstance(cached_payload, dict):
            age_seconds = (datetime.now(UTC) - captured_at).total_seconds()
            if age_seconds < 60:
                return cached_payload

    payload = _run_workspace_probe()
    with PROBE_LOCK:
        PROBE_CACHE["captured_at"] = datetime.now(UTC)
        PROBE_CACHE["payload"] = payload
    return payload


def _run_workspace_probe() -> dict[str, dict[str, object]]:
    auth = _google_auth_status()
    docs_probe = {
        "label": "Google Docs MCP",
        "status": "warning" if not auth["token_available"] else "active",
        "detail": (
            "Google token missing; Docs append is blocked."
            if not auth["token_available"]
            else "Google Docs path looks healthy."
        ),
    }
    gmail_probe = {
        "label": "Gmail MCP",
        "status": "warning" if not auth["token_available"] else "active",
        "detail": (
            "Google token missing; Gmail draft/send is blocked."
            if not auth["token_available"]
            else "Gmail path looks healthy."
        ),
    }
    if not auth["token_available"]:
        return {"docs": docs_probe, "gmail": gmail_probe}

    try:
        creds = get_creds()
        get_drive_service(creds).files().list(
            q=f"mimeType='{GOOGLE_DOC_MIME_TYPE}' and trashed=false",
            fields="files(id)",
            pageSize=1,
            spaces="drive",
        ).execute()
    except HTTPException as exc:
        docs_probe["status"] = "error"
        docs_probe["detail"] = str(exc.detail)
    except Exception as exc:
        docs_probe["status"] = "error"
        docs_probe["detail"] = str(exc)

    try:
        creds = get_creds()
        get_gmail_service(creds).users().getProfile(userId="me").execute()
    except HTTPException as exc:
        gmail_probe["status"] = "error"
        gmail_probe["detail"] = str(exc.detail)
    except Exception as exc:
        gmail_probe["status"] = "error"
        gmail_probe["detail"] = str(exc)

    return {"docs": docs_probe, "gmail": gmail_probe}


def _delivery_event_matches_product(event, runs) -> bool:
    run_ids = {run.run_id for run in runs}
    return event.run_id in run_ids
