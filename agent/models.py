from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    PLANNED = "planned"
    INGESTING = "ingesting"
    INGESTED = "ingested"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    SUMMARIZING = "summarizing"
    SUMMARIZED = "summarized"
    RENDERING = "rendering"
    RENDERED = "rendered"
    PUBLISHING_DOCS = "publishing_docs"
    PUBLISHED_DOCS = "published_docs"
    PUBLISHING_GMAIL = "publishing_gmail"
    COMPLETED = "completed"
    FAILED = "failed"


class RawReview(BaseModel):
    review_id: str
    product_key: str
    source: str
    external_id: str
    rating: int = Field(ge=1, le=5)
    title: str | None = None
    body_raw: str
    body_scrubbed: str
    reviewed_at: datetime
    locale: str | None = None
    raw_payload: dict[str, object]


class Theme(BaseModel):
    name: str
    summary: str
    review_count: int = Field(ge=0)
    sentiment: str
    quotes: list[str] = Field(default_factory=list)
    action_ideas: list[str] = Field(default_factory=list)


class PulseReport(BaseModel):
    run_id: str
    product_key: str
    product_name: str
    iso_week: str
    window_start: date
    window_end: date
    top_themes: list[Theme] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    action_ideas: list[str] = Field(default_factory=list)
    who_this_helps: list[str] = Field(default_factory=list)
    report_anchor: str


class LLMUsage(BaseModel):
    provider: str
    model: str
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    retries: int = Field(default=0, ge=0)


class DeliveryResult(BaseModel):
    gdoc_id: str | None = None
    gdoc_heading_id: str | None = None
    gdoc_deep_link: str | None = None
    gmail_draft_id: str | None = None
    gmail_message_id: str | None = None
    delivery_status: str


class DocsContentBlock(BaseModel):
    kind: Literal["heading", "paragraph", "bullet_list"]
    text: str | None = None
    items: list[str] = Field(default_factory=list)
    level: int | None = None


class DocsAppendPayload(BaseModel):
    document_title: str
    section_anchor: str
    heading: str
    blocks: list[DocsContentBlock] = Field(default_factory=list)


class DocsDocumentState(BaseModel):
    document_id: str
    title: str
    doc_url: str
    text_content: str
    heading_lookup: dict[str, str] = Field(default_factory=dict)


class EmailRenderPayload(BaseModel):
    subject: str
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    doc_link_placeholder: str
    html_body: str
    text_body: str


class RunRecord(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    status: RunStatus
    window_start: date
    window_end: date
    report_anchor: str


class IngestionResult(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    fetched: int
    inserted: int
    updated: int
    unchanged: int
    raw_snapshot_path: str
    sources: dict[str, int] = Field(default_factory=dict)


class AnalysisCluster(BaseModel):
    cluster_id: str
    cluster_index: int
    review_ids: list[str] = Field(default_factory=list)
    review_count: int = Field(ge=0)
    representative_review_id: str
    keyphrases: list[str] = Field(default_factory=list)
    sentiment_score: float = 0.0
    noise: bool = False


class AnalysisResult(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    eligible_reviews: int = Field(ge=0)
    filtered_reviews: int = Field(ge=0)
    clusters_formed: int = Field(ge=0)
    noise_reviews: int = Field(ge=0)
    embedding_cache_hits: int = Field(ge=0)
    embedding_cache_misses: int = Field(ge=0)
    embedding_model: str
    artifact_path: str
    clusters: list[AnalysisCluster] = Field(default_factory=list)


class SummarizationResult(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    summary_path: str
    usage: LLMUsage
    report: PulseReport


class RenderResult(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    artifact_dir: str
    doc_payload_path: str
    email_html_path: str
    email_text_path: str
    docs_heading: str
    email_subject: str
    doc_link_placeholder: str
    docs_payload_size_bytes: int = Field(ge=0)
    email_html_size_bytes: int = Field(ge=0)
    email_text_size_bytes: int = Field(ge=0)


class DocsPublishResult(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    section_anchor: str
    doc_title: str
    gdoc_id: str
    gdoc_heading_id: str | None = None
    gdoc_deep_link: str
    delivery_status: str
    created_doc: bool = False
    skipped: bool = False
    docs_mcp_calls: int = Field(default=0, ge=0)


class GmailSearchMatch(BaseModel):
    message_id: str
    draft_id: str | None = None
    label_ids: list[str] = Field(default_factory=list)
    subject: str | None = None


class GmailDraftResult(BaseModel):
    draft_id: str
    message_id: str


class GmailSendResult(BaseModel):
    message_id: str


class GmailPublishResult(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    email_subject: str
    recipients: list[str] = Field(default_factory=list)
    gdoc_deep_link: str
    gmail_draft_id: str | None = None
    gmail_message_id: str | None = None
    delivery_status: str
    draft_only: bool = False
    skipped: bool = False
    gmail_mcp_calls: int = Field(default=0, ge=0)


class PipelinePhaseResult(BaseModel):
    phase: str
    status: Literal["executed", "skipped"]
    attempts: int = Field(default=1, ge=1)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    detail: str | None = None


class PipelineRunResult(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    initial_status: str
    final_status: str
    draft_only: bool = False
    resumed: bool = False
    phase_results: list[PipelinePhaseResult] = Field(default_factory=list)
    total_duration_seconds: float = Field(default=0.0, ge=0.0)
    llm_total_tokens: int = Field(default=0, ge=0)
    llm_cost_usd: float = Field(default=0.0, ge=0.0)
    error_message: str | None = None


class RunHistoryEntry(BaseModel):
    run_id: str
    product_key: str
    iso_week: str
    status: str
    started_at: str
    completed_at: str | None = None
    gdoc_deep_link: str | None = None
    gmail_draft_id: str | None = None
    gmail_message_id: str | None = None
    error_message: str | None = None


class DeliveryEventEntry(BaseModel):
    event_id: int
    run_id: str
    channel: str
    status: str
    external_id: str | None = None
    occurred_at: str
