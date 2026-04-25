from __future__ import annotations

from pathlib import Path
from time import perf_counter

from agent.config import ProductConfig, RuntimeSettings
from agent.models import EmailRenderPayload, RenderResult, RunRecord, RunStatus
from agent.rendering.docs import render_docs_payload
from agent.rendering.email import render_email_payload
from agent.storage import fetch_report, update_run_render_result, update_run_status


def render_run(
    *,
    settings: RuntimeSettings,
    database_path: Path,
    product: ProductConfig,
    run: RunRecord,
) -> RenderResult:
    update_run_status(database_path, run.run_id, RunStatus.RENDERING)
    try:
        report = fetch_report(database_path, run.run_id)
        if report is None:
            msg = "No summarized report available for rendering"
            raise RuntimeError(msg)

        started = perf_counter()
        docs_payload = render_docs_payload(report)
        email_payload = render_email_payload(report, product)
        artifact_dir = _resolve_artifact_dir(settings, run.run_id)
        doc_payload_path = artifact_dir / "doc_payload.json"
        email_html_path = artifact_dir / "email.html"
        email_text_path = artifact_dir / "email.txt"
        _write_artifacts(
            artifact_dir=artifact_dir,
            doc_payload_path=doc_payload_path,
            email_html_path=email_html_path,
            email_text_path=email_text_path,
            docs_payload=docs_payload.model_dump_json(indent=2),
            email_payload=email_payload,
        )
        _ = perf_counter() - started

        result = RenderResult(
            run_id=run.run_id,
            product_key=run.product_key,
            iso_week=run.iso_week,
            artifact_dir=str(artifact_dir),
            doc_payload_path=str(doc_payload_path),
            email_html_path=str(email_html_path),
            email_text_path=str(email_text_path),
            docs_heading=docs_payload.heading,
            email_subject=email_payload.subject,
            doc_link_placeholder=email_payload.doc_link_placeholder,
            docs_payload_size_bytes=doc_payload_path.stat().st_size,
            email_html_size_bytes=email_html_path.stat().st_size,
            email_text_size_bytes=email_text_path.stat().st_size,
        )
        update_run_render_result(database_path, run.run_id, result)
        return result
    except Exception as exc:
        update_run_status(database_path, run.run_id, RunStatus.FAILED, error_message=str(exc))
        raise


def _resolve_artifact_dir(settings: RuntimeSettings, run_id: str) -> Path:
    artifact_dir = settings.resolve_database_path().parent / "rendered" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _write_artifacts(
    *,
    artifact_dir: Path,
    doc_payload_path: Path,
    email_html_path: Path,
    email_text_path: Path,
    docs_payload: str,
    email_payload: EmailRenderPayload,
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    doc_payload_path.write_text(docs_payload + "\n", encoding="utf-8")
    email_html_path.write_text(email_payload.html_body + "\n", encoding="utf-8")
    email_text_path.write_text(email_payload.text_body, encoding="utf-8")
