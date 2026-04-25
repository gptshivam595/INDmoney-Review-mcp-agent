from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from agent.config import load_product_catalog, load_runtime_settings
from agent.mcp.docs_service import publish_docs_run
from agent.models import DocsAppendPayload, DocsDocumentState, PulseReport, RunStatus, Theme
from agent.rendering.service import render_run
from agent.storage import (
    create_or_get_run,
    fetch_run,
    initialize_database,
    sync_products,
    upsert_report,
)
from agent.windowing import build_review_window


@dataclass
class FakeDocsClient:
    documents: dict[str, DocsDocumentState] = field(default_factory=dict)
    title_to_id: dict[str, str] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    next_id: int = 1

    def ensure_document(self, title: str) -> tuple[DocsDocumentState, bool]:
        self.calls.append("ensure_document")
        document_id = self.title_to_id.get(title)
        if document_id is None:
            document_id = f"doc-{self.next_id}"
            self.next_id += 1
            state = DocsDocumentState(
                document_id=document_id,
                title=title,
                doc_url=f"https://docs.google.com/document/d/{document_id}",
                text_content="",
                heading_lookup={},
            )
            self.documents[document_id] = state
            self.title_to_id[title] = document_id
            return state, True
        return self.documents[document_id], False

    def get_document(self, document_id: str) -> DocsDocumentState:
        self.calls.append("get_document")
        return self.documents[document_id]

    def append_section(self, document_id: str, payload: DocsAppendPayload) -> None:
        self.calls.append("append_section")
        state = self.documents[document_id]
        section_text = "\n".join(
            [block.text for block in payload.blocks if block.text]
        )
        self.documents[document_id] = state.model_copy(
            update={
                "text_content": f"{state.text_content}\n{section_text}".strip(),
                "heading_lookup": {**state.heading_lookup, payload.heading: "heading-1"},
            }
        )


def test_publish_docs_run_appends_once_and_persists_metadata(
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

    client = FakeDocsClient()
    result = publish_docs_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        client=client,
    )

    stored_run = fetch_run(database_path, run.run_id)
    connection = sqlite3.connect(database_path)
    run_row = connection.execute(
        "SELECT gdoc_id, gdoc_heading_id, gdoc_deep_link, metrics_json FROM runs WHERE run_id = ?",
        (run.run_id,),
    ).fetchone()
    event_row = connection.execute(
        "SELECT channel, status FROM delivery_events WHERE run_id = ?",
        (run.run_id,),
    ).fetchone()
    assert run_row is not None
    assert event_row is not None
    metrics = json.loads(run_row[3])

    assert client.calls == [
        "ensure_document",
        "get_document",
        "append_section",
        "get_document",
    ]
    assert result.delivery_status == "appended"
    assert result.created_doc is True
    assert result.skipped is False
    assert stored_run.status == RunStatus.PUBLISHED_DOCS
    assert run_row[0] == result.gdoc_id
    assert run_row[1] == "heading-1"
    assert run_row[2] == f"https://docs.google.com/document/d/{result.gdoc_id}/edit#heading=heading-1"
    assert metrics["publish_docs"]["delivery_status"] == "appended"
    assert event_row[0] == "docs"
    assert event_row[1] == "appended"


def test_publish_docs_run_skips_when_anchor_already_exists(
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

    client = FakeDocsClient()
    publish_docs_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        client=client,
    )

    client.calls.clear()
    result = publish_docs_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
        client=client,
    )

    assert client.calls == ["ensure_document", "get_document"]
    assert result.delivery_status == "skipped"
    assert result.skipped is True


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
