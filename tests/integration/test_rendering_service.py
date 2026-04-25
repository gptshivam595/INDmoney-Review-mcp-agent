from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from agent.config import load_product_catalog, load_runtime_settings
from agent.models import PulseReport, RunStatus, Theme
from agent.rendering.email import DOC_LINK_PLACEHOLDER
from agent.rendering.service import render_run
from agent.storage import (
    create_or_get_run,
    fetch_run,
    initialize_database,
    sync_products,
    upsert_report,
)
from agent.windowing import build_review_window


def test_render_run_writes_deterministic_artifacts_and_updates_run(
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

    first = render_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
    )
    doc_bytes = Path(first.doc_payload_path).read_bytes()
    html_bytes = Path(first.email_html_path).read_bytes()
    text_bytes = Path(first.email_text_path).read_bytes()

    second = render_run(
        settings=settings,
        database_path=database_path,
        product=catalog.get_product("indmoney"),
        run=run,
    )

    stored_run = fetch_run(database_path, run.run_id)
    connection = sqlite3.connect(database_path)
    row = connection.execute(
        "SELECT artifact_dir, metrics_json FROM runs WHERE run_id = ?",
        (run.run_id,),
    ).fetchone()
    assert row is not None
    metrics = json.loads(row[1])
    doc_payload = json.loads(Path(second.doc_payload_path).read_text(encoding="utf-8"))

    assert stored_run.status == RunStatus.RENDERED
    assert Path(second.doc_payload_path).read_bytes() == doc_bytes
    assert Path(second.email_html_path).read_bytes() == html_bytes
    assert Path(second.email_text_path).read_bytes() == text_bytes
    assert doc_payload["section_anchor"] == run.report_anchor
    assert DOC_LINK_PLACEHOLDER in Path(second.email_text_path).read_text(encoding="utf-8")
    assert row[0] == second.artifact_dir
    assert metrics["rendering"]["doc_link_placeholder"] == DOC_LINK_PLACEHOLDER


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
            ),
            Theme(
                name="Customer support friction",
                summary="Users report slow replies and weak ticket visibility.",
                review_count=2,
                sentiment="negative",
                quotes=["Support replies are slow and ticket status stays pending."],
                action_ideas=["Expose ticket status updates inside the app."],
            ),
        ],
        quotes=[
            "App crashes during login and market open.",
            "Support replies are slow and ticket status stays pending.",
        ],
        action_ideas=[
            "Stabilize login reliability during peak market hours.",
            "Expose ticket status updates inside the app.",
        ],
        who_this_helps=[
            "Product: prioritize the recurring product issues.",
            "Support: tighten follow-up expectations.",
        ],
        report_anchor=anchor,
    )
