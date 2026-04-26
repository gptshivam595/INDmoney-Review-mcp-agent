from __future__ import annotations

from pathlib import Path

from agent.config import ProductConfig, RuntimeSettings
from agent.mcp.gmail_client import GmailMCPClient, load_gmail_client
from agent.models import EmailRenderPayload, GmailPublishResult, RunRecord, RunStatus
from agent.rendering.email import render_email_payload
from agent.storage import (
    fetch_delivery_result,
    fetch_report,
    record_delivery_event,
    update_run_gmail_publish_result,
    update_run_status,
)


def publish_gmail_run(
    *,
    settings: RuntimeSettings,
    database_path: Path,
    product: ProductConfig,
    run: RunRecord,
    draft_only: bool,
    client: GmailMCPClient | None = None,
) -> GmailPublishResult:
    update_run_status(database_path, run.run_id, RunStatus.PUBLISHING_GMAIL)
    partial_result: GmailPublishResult | None = None
    try:
        delivery_result = fetch_delivery_result(database_path, run.run_id)
        if delivery_result is None or not delivery_result.gdoc_deep_link:
            msg = "Gmail publish requires a confirmed Google Docs deep link"
            raise RuntimeError(msg)

        report = fetch_report(database_path, run.run_id)
        if report is None:
            msg = "No summarized report available for Gmail delivery"
            raise RuntimeError(msg)

        final_email = render_email_payload(
            report,
            product,
            doc_link=delivery_result.gdoc_deep_link,
        )
        recipients = _flatten_recipients(final_email)
        if not recipients:
            msg = "Gmail publish requires at least one recipient"
            raise RuntimeError(msg)
        _validate_recipients(recipients)

        gmail_client = client or load_gmail_client(settings)
        gmail_mcp_calls = 0
        search_query = f"\"Run id: {run.run_id}\""
        search_matches = gmail_client.search_messages(search_query)
        gmail_mcp_calls += 1

        existing_message_id = delivery_result.gmail_message_id
        existing_draft_id = delivery_result.gmail_draft_id
        if search_matches:
            existing = search_matches[0]
            if existing.draft_id:
                existing_draft_id = existing.draft_id
            else:
                existing_message_id = existing.message_id

        effective_draft_only = draft_only or not settings.confirm_send
        if existing_draft_id or existing_message_id:
            if existing_draft_id and not existing_message_id and not effective_draft_only:
                send_result = gmail_client.send_draft(existing_draft_id)
                gmail_mcp_calls += 1
                result = GmailPublishResult(
                    run_id=run.run_id,
                    product_key=run.product_key,
                    iso_week=run.iso_week,
                    email_subject=final_email.subject,
                    recipients=recipients,
                    gdoc_deep_link=delivery_result.gdoc_deep_link,
                    gmail_draft_id=existing_draft_id,
                    gmail_message_id=send_result.message_id,
                    delivery_status="sent",
                    draft_only=False,
                    skipped=False,
                    gmail_mcp_calls=gmail_mcp_calls,
                )
                update_run_gmail_publish_result(database_path, run.run_id, result)
                record_delivery_event(
                    database_path,
                    run_id=run.run_id,
                    channel="gmail",
                    idempotency_key=f"{run.run_id}:gmail-send",
                    status=result.delivery_status,
                    external_id=result.gmail_message_id,
                    payload=final_email.model_dump(mode="json"),
                    metadata=result.model_dump(mode="json"),
                )
                return result

            result = GmailPublishResult(
                run_id=run.run_id,
                product_key=run.product_key,
                iso_week=run.iso_week,
                email_subject=final_email.subject,
                recipients=recipients,
                gdoc_deep_link=delivery_result.gdoc_deep_link,
                gmail_draft_id=existing_draft_id,
                gmail_message_id=existing_message_id,
                delivery_status="skipped",
                draft_only=effective_draft_only,
                skipped=True,
                gmail_mcp_calls=gmail_mcp_calls,
            )
            update_run_gmail_publish_result(database_path, run.run_id, result)
            record_delivery_event(
                database_path,
                run_id=run.run_id,
                channel="gmail",
                idempotency_key=run.run_id,
                status=result.delivery_status,
                external_id=result.gmail_message_id or result.gmail_draft_id,
                payload={"search_query": search_query},
                metadata=result.model_dump(mode="json"),
            )
            return result

        draft_result = gmail_client.create_draft(final_email)
        gmail_mcp_calls += 1
        partial_result = GmailPublishResult(
            run_id=run.run_id,
            product_key=run.product_key,
            iso_week=run.iso_week,
            email_subject=final_email.subject,
            recipients=recipients,
            gdoc_deep_link=delivery_result.gdoc_deep_link,
            gmail_draft_id=draft_result.draft_id,
            gmail_message_id=None,
            delivery_status="drafted",
            draft_only=effective_draft_only,
            skipped=False,
            gmail_mcp_calls=gmail_mcp_calls,
        )
        if effective_draft_only:
            update_run_gmail_publish_result(database_path, run.run_id, partial_result)
            record_delivery_event(
                database_path,
                run_id=run.run_id,
                channel="gmail",
                idempotency_key=run.run_id,
                status=partial_result.delivery_status,
                external_id=partial_result.gmail_draft_id,
                payload=final_email.model_dump(mode="json"),
                metadata=partial_result.model_dump(mode="json"),
            )
            return partial_result

        send_result = gmail_client.send_draft(draft_result.draft_id)
        gmail_mcp_calls += 1
        final_result = partial_result.model_copy(
            update={
                "gmail_message_id": send_result.message_id,
                "delivery_status": "sent",
                "draft_only": False,
                "gmail_mcp_calls": gmail_mcp_calls,
            }
        )
        update_run_gmail_publish_result(database_path, run.run_id, final_result)
        record_delivery_event(
            database_path,
            run_id=run.run_id,
            channel="gmail",
            idempotency_key=run.run_id,
            status=final_result.delivery_status,
            external_id=final_result.gmail_message_id,
            payload=final_email.model_dump(mode="json"),
            metadata=final_result.model_dump(mode="json"),
        )
        return final_result
    except Exception as exc:
        if partial_result is not None:
            update_run_gmail_publish_result(database_path, run.run_id, partial_result)
        update_run_status(database_path, run.run_id, RunStatus.FAILED, error_message=str(exc))
        raise


def _flatten_recipients(payload: EmailRenderPayload) -> list[str]:
    return payload.to + payload.cc + payload.bcc


def _validate_recipients(recipients: list[str]) -> None:
    invalid = [recipient for recipient in recipients if "@" not in recipient]
    if invalid:
        msg = f"Invalid recipient addresses: {invalid}"
        raise RuntimeError(msg)
