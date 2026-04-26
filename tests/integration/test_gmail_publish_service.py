from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from agent.config import load_product_catalog, load_runtime_settings
from agent.mcp.gmail_service import publish_gmail_run
from agent.models import DocsPublishResult, GmailSearchMatch, PulseReport, RunStatus, Theme
from agent.rendering.service import render_run
from agent.storage import (
    create_or_get_run,
    fetch_run,
    initialize_database,
    sync_products,
    update_run_docs_publish_result,
    upsert_report,
)
from agent.windowing import build_review_window


@dataclass
class FakeGmailClient:
    messages: list[dict[str, str | None]] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    draft_counter: int = 1
    message_counter: int = 1

    def search_messages(self, query: str) -> list[GmailSearchMatch]:
        self.calls.append("search_messages")
        needle = query.replace('"', "")
        matches = [
            GmailSearchMatch(
                message_id=entry["message_id"] or "",
                draft_id=entry["draft_id"],
                label_ids=["DRAFT"] if entry["draft_id"] else ["SENT"],
                subject=entry["subject"],
            )
            for entry in self.messages
            if needle in (entry["text_body"] or "")
        ]
        return matches

    def create_draft(self, payload) -> object:
        self.calls.append("create_draft")
        draft_id = f"draft-{self.draft_counter}"
        message_id = f"msg-{self.message_counter}"
        self.draft_counter += 1
        self.message_counter += 1
        self.messages.append(
            {
                "draft_id": draft_id,
                "message_id": message_id,
                "subject": payload.subject,
                "text_body": payload.text_body,
            }
        )
        return type("DraftResult", (), {"draft_id": draft_id, "message_id": message_id})()

    def send_draft(self, draft_id: str) -> object:
        self.calls.append("send_draft")
        for entry in self.messages:
            if entry["draft_id"] == draft_id:
                entry["draft_id"] = None
                return type("SendResult", (), {"message_id": entry["message_id"]})()
        raise AssertionError(f"Unknown draft id: {draft_id}")


def test_publish_gmail_run_creates_draft_and_skips_duplicate_rerun(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path, catalog, settings, run = prepare_rendered_run(tmp_path, monkeypatch)
    client = FakeGmailClient()

    first = publish_gmail_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        draft_only=True,
        client=client,
    )
    client.calls.clear()
    second = publish_gmail_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        draft_only=True,
        client=client,
    )

    stored_run = fetch_run(database_path, run.run_id)
    connection = sqlite3.connect(database_path)
    run_row = connection.execute(
        "SELECT gmail_draft_id, gmail_message_id, metrics_json FROM runs WHERE run_id = ?",
        (run.run_id,),
    ).fetchone()
    assert run_row is not None
    metrics = json.loads(run_row[2])

    assert first.delivery_status == "drafted"
    assert first.gmail_draft_id == "draft-1"
    assert second.delivery_status == "skipped"
    assert second.skipped is True
    assert client.calls == ["search_messages"]
    assert stored_run.status == RunStatus.COMPLETED
    assert run_row[0] == "draft-1"
    assert run_row[1] is None
    assert metrics["publish_gmail"]["delivery_status"] == "skipped"


def test_publish_gmail_run_sends_when_confirmed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path, catalog, settings, run = prepare_rendered_run(tmp_path, monkeypatch)
    settings = settings.model_copy(update={"confirm_send": True})
    client = FakeGmailClient()

    result = publish_gmail_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        draft_only=False,
        client=client,
    )

    connection = sqlite3.connect(database_path)
    run_row = connection.execute(
        "SELECT gmail_draft_id, gmail_message_id FROM runs WHERE run_id = ?",
        (run.run_id,),
    ).fetchone()
    assert run_row is not None

    assert client.calls == ["search_messages", "create_draft", "send_draft"]
    assert result.delivery_status == "sent"
    assert result.gmail_draft_id == "draft-1"
    assert result.gmail_message_id == "msg-1"
    assert run_row[0] == "draft-1"
    assert run_row[1] == "msg-1"


def test_publish_gmail_run_sends_existing_draft_when_confirmed_later(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path, catalog, settings, run = prepare_rendered_run(tmp_path, monkeypatch)
    settings = settings.model_copy(update={"confirm_send": True})
    client = FakeGmailClient()

    draft = publish_gmail_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        draft_only=True,
        client=client,
    )
    client.calls.clear()
    sent = publish_gmail_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        draft_only=False,
        client=client,
    )

    connection = sqlite3.connect(database_path)
    run_row = connection.execute(
        "SELECT gmail_draft_id, gmail_message_id FROM runs WHERE run_id = ?",
        (run.run_id,),
    ).fetchone()
    events = connection.execute(
        "SELECT status, external_id FROM delivery_events WHERE channel = 'gmail' ORDER BY event_id",
    ).fetchall()

    assert draft.delivery_status == "drafted"
    assert sent.delivery_status == "sent"
    assert sent.gmail_draft_id == "draft-1"
    assert sent.gmail_message_id == "msg-1"
    assert client.calls == ["search_messages", "send_draft"]
    assert run_row == ("draft-1", "msg-1")
    assert events == [("drafted", "draft-1"), ("sent", "msg-1")]


def test_publish_gmail_run_blocks_when_docs_link_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    initialize_database(database_path)
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    sync_products(database_path, catalog)
    settings = load_runtime_settings()
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    report = make_report(run.run_id, run.report_anchor)
    summary_path = tmp_path / "summaries" / f"{run.run_id}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    upsert_report(database_path, run.run_id, report, summary_path)
    render_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
    )

    with pytest.raises(RuntimeError, match="Google Docs deep link"):
        publish_gmail_run(
            settings=settings,
            database_path=database_path,
            product=catalog.get_product("indmoney"),
            run=run,
            draft_only=True,
            client=FakeGmailClient(),
        )


def prepare_rendered_run(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    initialize_database(database_path)
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    sync_products(database_path, catalog)
    settings = load_runtime_settings()
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    report = make_report(run.run_id, run.report_anchor)
    summary_path = tmp_path / "summaries" / f"{run.run_id}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    upsert_report(database_path, run.run_id, report, summary_path)
    render_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
    )
    update_run_docs_publish_result(
        database_path,
        run.run_id,
        DocsPublishResult(
            run_id=run.run_id,
            product_key=run.product_key,
            iso_week=run.iso_week,
            section_anchor=run.report_anchor,
            doc_title="Weekly Review Pulse - INDMoney",
            gdoc_id="doc-1",
            gdoc_heading_id="heading-1",
            gdoc_deep_link="https://docs.google.com/document/d/doc-1/edit#heading=heading-1",
            delivery_status="appended",
            created_doc=True,
            skipped=False,
            docs_mcp_calls=4,
        ),
    )
    return database_path, catalog, settings, run


def make_report(run_id: str, anchor: str) -> PulseReport:
    return PulseReport(
        run_id=run_id,
        product_key="indmoney",
        product_name="INDMoney",
        iso_week="2026-W17",
        window_start=date(2026, 2, 16),
        window_end=date(2026, 4, 26),
        top_themes=[
            Theme(
                name="App performance and reliability",
                summary="Customers report recurring crashes during login and market open.",
                review_count=3,
                sentiment="negative",
                quotes=["App crashes during login and market open."],
                action_ideas=["Stabilize login reliability during peak market hours."],
            )
        ],
        quotes=["App crashes during login and market open."],
        action_ideas=["Stabilize login reliability during peak market hours."],
        who_this_helps=["Product: prioritize the recurring product issues."],
        report_anchor=anchor,
    )
