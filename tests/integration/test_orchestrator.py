from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from agent.config import load_product_catalog, load_runtime_settings
from agent.mcp.docs_client import DocsMCPTransportError
from agent.models import DocsAppendPayload, DocsDocumentState, GmailSearchMatch, RawReview
from agent.orchestrator import PipelineDependencies, run_product_pipeline


@dataclass
class FakeDocsClient:
    documents: dict[str, DocsDocumentState] = field(default_factory=dict)
    title_to_id: dict[str, str] = field(default_factory=dict)
    append_calls: int = 0
    fail_first_append: bool = False

    def ensure_document(self, title: str) -> tuple[DocsDocumentState, bool]:
        document_id = self.title_to_id.get(title)
        if document_id is None:
            document_id = "doc-1"
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
        return self.documents[document_id]

    def append_section(self, document_id: str, payload: DocsAppendPayload) -> None:
        self.append_calls += 1
        if self.fail_first_append and self.append_calls == 1:
            raise DocsMCPTransportError("temporary docs outage")
        state = self.documents[document_id]
        text_content = f"{state.text_content}\n{payload.heading}".strip()
        self.documents[document_id] = state.model_copy(
            update={
                "text_content": text_content,
                "heading_lookup": {**state.heading_lookup, payload.heading: "heading-1"},
            }
        )


@dataclass
class FakeGmailClient:
    messages: list[dict[str, str | None]] = field(default_factory=list)
    create_calls: int = 0
    send_calls: int = 0
    fail_first_create: bool = False

    def search_messages(self, query: str) -> list[GmailSearchMatch]:
        needle = query.replace('"', "")
        return [
            GmailSearchMatch(
                message_id=entry["message_id"] or "",
                draft_id=entry["draft_id"],
                label_ids=["DRAFT"] if entry["draft_id"] else ["SENT"],
                subject=entry["subject"],
            )
            for entry in self.messages
            if needle in (entry["text_body"] or "")
        ]

    def create_draft(self, payload):
        self.create_calls += 1
        if self.fail_first_create and self.create_calls == 1:
            raise RuntimeError("gmail draft creation failed")
        draft_id = f"draft-{self.create_calls}"
        message_id = f"msg-{self.create_calls}"
        self.messages.append(
            {
                "draft_id": draft_id,
                "message_id": message_id,
                "subject": payload.subject,
                "text_body": payload.text_body,
            }
        )
        return type("DraftResult", (), {"draft_id": draft_id, "message_id": message_id})()

    def send_draft(self, draft_id: str):
        self.send_calls += 1
        return type("SendResult", (), {"message_id": draft_id.replace("draft", "msg")})()


class FakeEmbeddingProvider:
    model_name = "fake-v1"

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        if "crash" in lowered or "freeze" in lowered or "login" in lowered:
            return [1.0, 0.0]
        return [0.0, 1.0]


def test_run_product_pipeline_completes_and_rerun_is_checkpoint_noop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings, catalog = prepare_runtime(tmp_path, monkeypatch)
    docs_client = FakeDocsClient()
    gmail_client = FakeGmailClient()

    result = run_product_pipeline(
        settings=settings,
        catalog=catalog,
        product_key="indmoney",
        iso_week="2026-W17",
        draft_only=True,
        dependencies=PipelineDependencies(
            appstore_fetcher=appstore_reviews,
            playstore_fetcher=playstore_reviews,
            docs_client=docs_client,
            gmail_client=gmail_client,
        ),
    )
    rerun = run_product_pipeline(
        settings=settings,
        catalog=catalog,
        product_key="indmoney",
        iso_week="2026-W17",
        draft_only=True,
        dependencies=PipelineDependencies(
            appstore_fetcher=appstore_reviews,
            playstore_fetcher=playstore_reviews,
            docs_client=docs_client,
            gmail_client=gmail_client,
        ),
    )

    assert result.final_status == "completed"
    assert [phase.phase for phase in result.phase_results] == [
        "ingest",
        "analyze",
        "summarize",
        "render",
        "publish-docs",
        "publish-gmail",
    ]
    assert docs_client.append_calls == 1
    assert gmail_client.create_calls == 1
    assert rerun.final_status == "completed"
    assert rerun.resumed is True
    assert all(phase.status == "skipped" for phase in rerun.phase_results)


def test_run_product_pipeline_resumes_after_docs_publish_without_duplicate_append(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings, catalog = prepare_runtime(tmp_path, monkeypatch)
    docs_client = FakeDocsClient()
    failing_gmail = FakeGmailClient(fail_first_create=True)

    with pytest.raises(RuntimeError, match="gmail draft creation failed"):
        run_product_pipeline(
            settings=settings,
            catalog=catalog,
            product_key="indmoney",
            iso_week="2026-W17",
            draft_only=True,
            dependencies=PipelineDependencies(
                appstore_fetcher=appstore_reviews,
                playstore_fetcher=playstore_reviews,
                docs_client=docs_client,
                gmail_client=failing_gmail,
            ),
        )

    resumed = run_product_pipeline(
        settings=settings,
        catalog=catalog,
        product_key="indmoney",
        iso_week="2026-W17",
        draft_only=True,
        dependencies=PipelineDependencies(
            appstore_fetcher=appstore_reviews,
            playstore_fetcher=playstore_reviews,
            docs_client=docs_client,
            gmail_client=FakeGmailClient(),
        ),
    )

    assert docs_client.append_calls == 1
    assert resumed.final_status == "completed"
    phase_lookup = {phase.phase: phase for phase in resumed.phase_results}
    assert phase_lookup["publish-docs"].status == "skipped"
    assert phase_lookup["publish-gmail"].status == "executed"


def test_run_product_pipeline_retries_transient_docs_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings, catalog = prepare_runtime(tmp_path, monkeypatch)
    settings = settings.model_copy(update={"orchestration_retry_attempts": 2})
    docs_client = FakeDocsClient(fail_first_append=True)

    result = run_product_pipeline(
        settings=settings,
        catalog=catalog,
        product_key="indmoney",
        iso_week="2026-W17",
        draft_only=True,
        dependencies=PipelineDependencies(
            appstore_fetcher=appstore_reviews,
            playstore_fetcher=playstore_reviews,
            docs_client=docs_client,
            gmail_client=FakeGmailClient(),
        ),
    )

    phase_lookup = {phase.phase: phase for phase in result.phase_results}
    assert result.final_status == "completed"
    assert phase_lookup["publish-docs"].attempts == 2
    assert docs_client.append_calls == 2


def prepare_runtime(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))
    monkeypatch.setenv("PULSE_ANALYSIS_SIMILARITY_THRESHOLD", "0.8")
    monkeypatch.setenv("PULSE_ANALYSIS_MIN_CLUSTER_SIZE", "2")
    monkeypatch.setattr(
        "agent.analysis.service.load_embedding_provider",
        lambda _settings: FakeEmbeddingProvider(),
    )
    settings = load_runtime_settings()
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    return settings, catalog


def appstore_reviews(_product, _since_date) -> list[RawReview]:
    return [
        make_review("a1", "App crashes during login and freezes at market open.", 1, "appstore"),
        make_review("a2", "App freezes at market open and crashes during login.", 1, "appstore"),
    ]


def playstore_reviews(_product, _since_date) -> list[RawReview]:
    return [
        make_review(
            "p1",
            "Support replies are slow and ticket status stays pending.",
            2,
            "playstore",
        ),
        make_review(
            "p2",
            "Ticket updates are poor and support responses are slow.",
            2,
            "playstore",
        ),
    ]


def make_review(review_id: str, body: str, rating: int, source: str) -> RawReview:
    return RawReview(
        review_id=f"{source}-{review_id}",
        product_key="indmoney",
        source=source,
        external_id=review_id,
        rating=rating,
        title=None,
        body_raw=body,
        body_scrubbed=body,
        reviewed_at=datetime.fromisoformat("2026-04-21T10:00:00+00:00"),
        locale="en-IN",
        raw_payload={"review_id": review_id},
    )
