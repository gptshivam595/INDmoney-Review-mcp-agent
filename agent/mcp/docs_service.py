from __future__ import annotations

from pathlib import Path

from agent.config import ProductConfig, RuntimeSettings
from agent.mcp.docs_client import DocsMCPClient, load_docs_client
from agent.models import (
    DocsAppendPayload,
    DocsDocumentState,
    DocsPublishResult,
    RunRecord,
    RunStatus,
)
from agent.storage import (
    fetch_render_result,
    record_delivery_event,
    update_run_docs_publish_result,
    update_run_status,
)


class DocsPublishIntegrityError(RuntimeError):
    """Raised when the Docs publish flow detects an unsafe document state."""


def publish_docs_run(
    *,
    settings: RuntimeSettings,
    database_path: Path,
    product: ProductConfig,
    run: RunRecord,
    client: DocsMCPClient | None = None,
) -> DocsPublishResult:
    del product
    update_run_status(database_path, run.run_id, RunStatus.PUBLISHING_DOCS)
    try:
        render_result = fetch_render_result(database_path, run.run_id)
        if render_result is None:
            msg = "No rendered Docs payload available for publishing"
            raise RuntimeError(msg)

        payload = _load_docs_payload(Path(render_result.doc_payload_path))
        docs_client = client or load_docs_client(settings)
        docs_mcp_calls = 0

        document_state, created_doc = docs_client.ensure_document(payload.document_title)
        docs_mcp_calls += 1
        before_append = docs_client.get_document(document_state.document_id)
        docs_mcp_calls += 1

        existing_anchor_matches = _count_anchor_matches(
            before_append.text_content,
            payload.section_anchor,
        )
        if existing_anchor_matches > 1:
            msg = f"Multiple existing anchors found for {payload.section_anchor}"
            raise DocsPublishIntegrityError(msg)

        if existing_anchor_matches == 1:
            result = _build_result(
                run=run,
                payload=payload,
                state=before_append,
                created_doc=created_doc,
                skipped=True,
                docs_mcp_calls=docs_mcp_calls,
            )
        else:
            docs_client.append_section(document_state.document_id, payload)
            docs_mcp_calls += 1
            after_append = docs_client.get_document(document_state.document_id)
            docs_mcp_calls += 1
            after_matches = _count_anchor_matches(
                after_append.text_content,
                payload.section_anchor,
            )
            if after_matches != 1:
                msg = (
                    f"Expected exactly one anchor after append for {payload.section_anchor}, "
                    f"found {after_matches}"
                )
                raise DocsPublishIntegrityError(msg)
            result = _build_result(
                run=run,
                payload=payload,
                state=after_append,
                created_doc=created_doc,
                skipped=False,
                docs_mcp_calls=docs_mcp_calls,
            )

        update_run_docs_publish_result(database_path, run.run_id, result)
        record_delivery_event(
            database_path,
            run_id=run.run_id,
            channel="docs",
            idempotency_key=run.run_id,
            status=result.delivery_status,
            external_id=result.gdoc_id,
            payload=payload.model_dump(mode="json"),
            metadata=result.model_dump(mode="json"),
        )
        return result
    except Exception as exc:
        update_run_status(database_path, run.run_id, RunStatus.FAILED, error_message=str(exc))
        raise


def _load_docs_payload(doc_payload_path: Path) -> DocsAppendPayload:
    if not doc_payload_path.exists():
        msg = f"Rendered Docs payload not found: {doc_payload_path}"
        raise FileNotFoundError(msg)
    return DocsAppendPayload.model_validate_json(doc_payload_path.read_text(encoding="utf-8"))


def _count_anchor_matches(text_content: str, section_anchor: str) -> int:
    return text_content.count(section_anchor)


def _build_result(
    *,
    run: RunRecord,
    payload: DocsAppendPayload,
    state: DocsDocumentState,
    created_doc: bool,
    skipped: bool,
    docs_mcp_calls: int,
) -> DocsPublishResult:
    heading_id = state.heading_lookup.get(payload.heading)
    deep_link = _build_deep_link(state.doc_url, heading_id)
    return DocsPublishResult(
        run_id=run.run_id,
        product_key=run.product_key,
        iso_week=run.iso_week,
        section_anchor=payload.section_anchor,
        doc_title=state.title,
        gdoc_id=state.document_id,
        gdoc_heading_id=heading_id,
        gdoc_deep_link=deep_link,
        delivery_status="skipped" if skipped else "appended",
        created_doc=created_doc,
        skipped=skipped,
        docs_mcp_calls=docs_mcp_calls,
    )


def _build_deep_link(doc_url: str, heading_id: str | None) -> str:
    if heading_id:
        return f"{doc_url}/edit#heading={heading_id}"
    return doc_url
