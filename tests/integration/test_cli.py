import json
from datetime import date, datetime
from pathlib import Path

from typer.testing import CliRunner

import agent.ingestion.service as ingestion_service
from agent.__main__ import app
from agent.config import load_product_catalog, load_runtime_settings
from agent.ingestion.appstore import parse_appstore_payload
from agent.ingestion.playstore import normalize_playstore_reviews
from agent.models import (
    AnalysisCluster,
    DocsAppendPayload,
    DocsDocumentState,
    DocsPublishResult,
    PipelinePhaseResult,
    PipelineRunResult,
    PulseReport,
    RawReview,
    Theme,
)
from agent.rendering.service import render_run
from agent.storage import (
    create_or_get_run,
    fetch_report,
    replace_clusters_for_run,
    update_run_docs_publish_result,
    upsert_report,
    upsert_reviews,
)
from agent.windowing import build_review_window

runner = CliRunner()


def test_cli_help_lists_phase_zero_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in [
        "init-db",
        "list-products",
        "plan-run",
        "ingest",
        "analyze",
        "summarize",
        "render",
        "publish-docs",
        "publish-gmail",
        "run",
    ]:
        assert command in result.stdout


def test_init_db_command_creates_database(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    result = runner.invoke(app, ["init-db"])

    assert result.exit_code == 0
    assert database_path.exists()


def test_plan_run_command_returns_planned_run(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    result = runner.invoke(app, ["plan-run", "--product", "indmoney", "--week", "2026-W17"])

    assert result.exit_code == 0
    assert "pulse-indmoney-2026-W17" in result.stdout


def test_ingest_command_persists_reviews(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    product = load_product_catalog(Path.cwd() / "products.yaml").get_product("indmoney")
    since_date = date(2026, 2, 16)
    appstore_payload = json.loads(
        (Path.cwd() / "tests/fixtures/appstore_reviews_page1.json").read_text(encoding="utf-8")
    )
    playstore_payload = json.loads(
        (Path.cwd() / "tests/fixtures/playstore_reviews_page1.json").read_text(encoding="utf-8")
    )

    monkeypatch.setattr(
        ingestion_service,
        "fetch_appstore_reviews",
        lambda _product, _since_date: parse_appstore_payload(product, appstore_payload, since_date),
    )
    monkeypatch.setattr(
        ingestion_service,
        "fetch_playstore_reviews",
        lambda _product, _since_date: normalize_playstore_reviews(
            product,
            playstore_payload,
            since_date,
        ),
    )

    result = runner.invoke(app, ["ingest", "--product", "indmoney", "--week", "2026-W17"])

    assert result.exit_code == 0
    assert '"inserted": 2' in result.stdout


def test_analyze_command_returns_clusters(tmp_path: Path, monkeypatch) -> None:
    class FakeEmbeddingProvider:
        model_name = "fake-v1"

        def embed(self, text: str) -> list[float]:
            lowered = text.lower()
            if "crash" in lowered or "freeze" in lowered:
                return [1.0, 0.0]
            return [0.0, 1.0]

    def make_review(review_id: str, body: str) -> RawReview:
        return RawReview(
            review_id=review_id,
            product_key="indmoney",
            source="fixture",
            external_id=review_id,
            rating=2,
            title=None,
            body_raw=body,
            body_scrubbed=body,
            reviewed_at=datetime.fromisoformat("2026-04-21T10:00:00+00:00"),
            locale="en-IN",
            raw_payload={"review_id": review_id},
        )

    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))
    monkeypatch.setenv("PULSE_ANALYSIS_SIMILARITY_THRESHOLD", "0.8")
    monkeypatch.setenv("PULSE_ANALYSIS_MIN_CLUSTER_SIZE", "2")

    runner.invoke(app, ["init-db"])
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    upsert_reviews(
        database_path,
        [
            make_review("r1", "App crashes during login and freezes at market open."),
            make_review("r2", "App freezes at market open and crashes during login."),
            make_review("r3", "Support replies are slow and ticket status stays pending."),
            make_review("r4", "Ticket updates are poor and support responses are slow."),
        ],
    )

    monkeypatch.setattr(
        "agent.analysis.service.load_embedding_provider",
        lambda _settings: FakeEmbeddingProvider(),
    )
    result = runner.invoke(app, ["analyze", "--run", run.run_id])

    assert result.exit_code == 0
    assert '"clusters_formed": 2' in result.stdout


def test_summarize_command_returns_report_artifact(tmp_path: Path, monkeypatch) -> None:
    def make_review(review_id: str, body: str) -> RawReview:
        return RawReview(
            review_id=review_id,
            product_key="indmoney",
            source="fixture",
            external_id=review_id,
            rating=2,
            title=None,
            body_raw=body,
            body_scrubbed=body,
            reviewed_at=datetime.fromisoformat("2026-04-21T10:00:00+00:00"),
            locale="en-IN",
            raw_payload={"review_id": review_id},
        )

    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    runner.invoke(app, ["init-db"])
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    upsert_reviews(
        database_path,
        [
            make_review("r1", "App crashes during market open and login keeps failing often."),
            make_review("r2", "Support replies are slow and ticket updates stay pending."),
        ],
    )
    replace_clusters_for_run(
        database_path,
        run.run_id,
        [
            AnalysisCluster(
                cluster_id="cluster-1",
                cluster_index=0,
                review_ids=["r1"],
                review_count=1,
                representative_review_id="r1",
                keyphrases=["crash", "login"],
                sentiment_score=-0.9,
                noise=False,
            ),
            AnalysisCluster(
                cluster_id="cluster-2",
                cluster_index=1,
                review_ids=["r2"],
                review_count=1,
                representative_review_id="r2",
                keyphrases=["support", "ticket"],
                sentiment_score=-0.6,
                noise=False,
            ),
        ],
    )

    result = runner.invoke(app, ["summarize", "--run", run.run_id])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert Path(payload["summary_path"]).exists()
    assert payload["report"]["run_id"] == run.run_id
    assert fetch_report(database_path, run.run_id) is not None


def test_render_command_returns_rendered_artifacts(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    runner.invoke(app, ["init-db"])
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    report = PulseReport(
        run_id=run.run_id,
        product_key="indmoney",
        product_name="INDMoney",
        iso_week=run.iso_week,
        window_start=run.window_start,
        window_end=run.window_end,
        top_themes=[
            Theme(
                name="App performance and reliability",
                summary="Customers report recurring crashes during login and market open.",
                review_count=2,
                sentiment="negative",
                quotes=["App crashes during login and market open."],
                action_ideas=["Stabilize login reliability during peak load."],
            )
        ],
        quotes=["App crashes during login and market open."],
        action_ideas=["Stabilize login reliability during peak load."],
        who_this_helps=["Product: prioritize the reliability fixes."],
        report_anchor=run.report_anchor,
    )
    summary_path = tmp_path / "summaries" / f"{run.run_id}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    upsert_report(database_path, run.run_id, report, summary_path)

    result = runner.invoke(app, ["render", "--run", run.run_id])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert Path(payload["doc_payload_path"]).exists()
    assert Path(payload["email_html_path"]).exists()
    assert Path(payload["email_text_path"]).exists()
    assert payload["docs_heading"] == (
        f"INDMoney - Weekly Review Pulse - {run.iso_week} - {run.report_anchor}"
    )


def test_publish_docs_command_returns_publish_result(tmp_path: Path, monkeypatch) -> None:
    class FakeDocsClient:
        def __init__(self) -> None:
            self.document = DocsDocumentState(
                document_id="doc-1",
                title="Weekly Review Pulse - INDMoney",
                doc_url="https://docs.google.com/document/d/doc-1",
                text_content="",
                heading_lookup={},
            )

        def ensure_document(self, title: str) -> tuple[DocsDocumentState, bool]:
            self.document = self.document.model_copy(update={"title": title})
            return self.document, True

        def get_document(self, document_id: str) -> DocsDocumentState:
            del document_id
            return self.document

        def append_section(self, document_id: str, payload: DocsAppendPayload) -> None:
            del document_id
            self.document = self.document.model_copy(
                update={
                    "text_content": f"{self.document.text_content}\n{payload.heading}".strip(),
                    "heading_lookup": {payload.heading: "heading-1"},
                }
            )

    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    runner.invoke(app, ["init-db"])
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    settings = load_runtime_settings()
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    report = PulseReport(
        run_id=run.run_id,
        product_key="indmoney",
        product_name="INDMoney",
        iso_week=run.iso_week,
        window_start=run.window_start,
        window_end=run.window_end,
        top_themes=[
            Theme(
                name="App performance and reliability",
                summary="Customers report recurring crashes during login and market open.",
                review_count=2,
                sentiment="negative",
                quotes=["App crashes during login and market open."],
                action_ideas=["Stabilize login reliability during peak load."],
            )
        ],
        quotes=["App crashes during login and market open."],
        action_ideas=["Stabilize login reliability during peak load."],
        who_this_helps=["Product: prioritize the reliability fixes."],
        report_anchor=run.report_anchor,
    )
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

    monkeypatch.setattr(
        "agent.mcp.docs_service.load_docs_client",
        lambda _settings: FakeDocsClient(),
    )

    result = runner.invoke(app, ["publish-docs", "--run", run.run_id])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["delivery_status"] == "appended"
    assert payload["gdoc_id"] == "doc-1"


def test_publish_gmail_command_returns_draft_result(tmp_path: Path, monkeypatch) -> None:
    class FakeGmailClient:
        def search_messages(self, query: str) -> list[object]:
            del query
            return []

        def create_draft(self, payload):
            del payload
            return type("DraftResult", (), {"draft_id": "draft-1", "message_id": "msg-1"})()

        def send_draft(self, draft_id: str):
            del draft_id
            return type("SendResult", (), {"message_id": "msg-1"})()

    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    runner.invoke(app, ["init-db"])
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    settings = load_runtime_settings()
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    report = PulseReport(
        run_id=run.run_id,
        product_key="indmoney",
        product_name="INDMoney",
        iso_week=run.iso_week,
        window_start=run.window_start,
        window_end=run.window_end,
        top_themes=[
            Theme(
                name="App performance and reliability",
                summary="Customers report recurring crashes during login and market open.",
                review_count=2,
                sentiment="negative",
                quotes=["App crashes during login and market open."],
                action_ideas=["Stabilize login reliability during peak load."],
            )
        ],
        quotes=["App crashes during login and market open."],
        action_ideas=["Stabilize login reliability during peak load."],
        who_this_helps=["Product: prioritize the reliability fixes."],
        report_anchor=run.report_anchor,
    )
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

    monkeypatch.setattr(
        "agent.mcp.gmail_service.load_gmail_client",
        lambda _settings: FakeGmailClient(),
    )

    result = runner.invoke(app, ["publish-gmail", "--run", run.run_id, "--draft-only"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["delivery_status"] == "drafted"
    assert payload["gmail_draft_id"] == "draft-1"


def test_run_command_returns_pipeline_result(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    monkeypatch.setattr(
        "agent.__main__.run_product_pipeline",
        lambda **_kwargs: PipelineRunResult(
            run_id="run-123",
            product_key="indmoney",
            iso_week="2026-W17",
            initial_status="planned",
            final_status="completed",
            draft_only=True,
            resumed=False,
            phase_results=[
                PipelinePhaseResult(
                    phase="ingest",
                    status="executed",
                    attempts=1,
                    duration_seconds=0.1,
                )
            ],
            total_duration_seconds=0.1,
            llm_total_tokens=12,
            llm_cost_usd=0.0,
            error_message=None,
        ),
    )

    result = runner.invoke(
        app,
        ["run", "--product", "indmoney", "--week", "2026-W17", "--draft-only"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["final_status"] == "completed"
    assert payload["draft_only"] is True
