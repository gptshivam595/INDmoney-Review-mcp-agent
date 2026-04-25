from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agent.config import load_product_catalog, load_runtime_settings
from agent.models import AnalysisCluster, LLMUsage, RawReview, RunStatus
from agent.storage import (
    create_or_get_run,
    fetch_report,
    fetch_run,
    initialize_database,
    replace_clusters_for_run,
    sync_products,
    upsert_reviews,
)
from agent.summarization.provider import ProviderResponse, ThemeSuggestion
from agent.summarization.service import PulseCostExceeded, summarize_run
from agent.windowing import build_review_window


class RetryingProvider:
    def __init__(self) -> None:
        self.quote_calls = 0

    def label_theme(
        self,
        cluster: AnalysisCluster,
        reviews: list[RawReview],
    ) -> ProviderResponse:
        del cluster, reviews
        return ProviderResponse(
            usage=_usage(cost_usd=0.2),
            payload=ThemeSuggestion(
                name="App performance and reliability",
                summary="Customers report recurring crashes during login and market open.",
                sentiment="negative",
            ),
        )

    def select_quotes(
        self,
        cluster: AnalysisCluster,
        reviews: list[RawReview],
        invalid_quotes: list[str] | None = None,
    ) -> ProviderResponse:
        del cluster, invalid_quotes
        self.quote_calls += 1
        if self.quote_calls == 1:
            return ProviderResponse(
                usage=_usage(cost_usd=0.2),
                payload=["This quote is not grounded in the reviews."],
            )
        return ProviderResponse(
            usage=_usage(cost_usd=0.2),
            payload=[reviews[0].body_scrubbed],
        )

    def generate_action_ideas(self, theme: ThemeSuggestion) -> ProviderResponse:
        del theme
        return ProviderResponse(
            usage=_usage(cost_usd=0.2),
            payload=[
                "Stabilize login reliability during peak market hours.",
                "Improve crash detection and recovery telemetry.",
            ],
        )


class ExpensiveProvider:
    def label_theme(
        self,
        cluster: AnalysisCluster,
        reviews: list[RawReview],
    ) -> ProviderResponse:
        del cluster, reviews
        return ProviderResponse(
            usage=_usage(cost_usd=0.6),
            payload=ThemeSuggestion(
                name="App performance and reliability",
                summary="Customers report recurring crashes during login and market open.",
                sentiment="negative",
            ),
        )

    def select_quotes(
        self,
        cluster: AnalysisCluster,
        reviews: list[RawReview],
        invalid_quotes: list[str] | None = None,
    ) -> ProviderResponse:
        del cluster, invalid_quotes
        return ProviderResponse(
            usage=_usage(cost_usd=0.6),
            payload=[reviews[0].body_scrubbed],
        )

    def generate_action_ideas(self, theme: ThemeSuggestion) -> ProviderResponse:
        del theme
        return ProviderResponse(
            usage=_usage(cost_usd=0.0),
            payload=["Stabilize the primary failure path."],
        )


def make_review(review_id: str, body: str, rating: int) -> RawReview:
    return RawReview(
        review_id=review_id,
        product_key="indmoney",
        source="fixture",
        external_id=review_id,
        rating=rating,
        title=None,
        body_raw=body,
        body_scrubbed=body,
        reviewed_at=datetime.fromisoformat("2026-04-21T10:00:00+00:00"),
        locale="en-IN",
        raw_payload={"review_id": review_id},
    )


def seed_reviews() -> list[RawReview]:
    return [
        make_review("r1", "App crashes during market open and login keeps failing often.", 1),
        make_review("r2", "The app freezes during market open and login stops working.", 1),
        make_review("r3", "Crashes and freezes happen at market open and login is unreliable.", 2),
    ]


def build_cluster() -> AnalysisCluster:
    return AnalysisCluster(
        cluster_id="cluster-1",
        cluster_index=0,
        review_ids=["r1", "r2", "r3"],
        review_count=3,
        representative_review_id="r1",
        keyphrases=["crash", "login", "market open"],
        sentiment_score=-0.9,
        noise=False,
    )


def test_summarize_run_retries_invalid_quotes_and_persists_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = _prepare_database(tmp_path, monkeypatch)
    settings = load_runtime_settings()
    run = _prepare_run(database_path)
    provider = RetryingProvider()

    monkeypatch.setattr(
        "agent.summarization.service.load_summarization_provider",
        lambda _provider, _model: provider,
    )

    result = summarize_run(
        settings=settings,
        database_path=database_path,
        product=load_product_catalog(Path.cwd() / "products.yaml").get_product("indmoney"),
        run=run,
    )

    stored_report = fetch_report(database_path, run.run_id)
    stored_run = fetch_run(database_path, run.run_id)

    assert provider.quote_calls == 2
    assert result.usage.retries == 1
    assert result.report.top_themes[0].quotes == [
        "App crashes during market open and login keeps failing often."
    ]
    assert Path(result.summary_path).exists()
    assert stored_report is not None
    assert stored_report.run_id == run.run_id
    assert stored_run.status == RunStatus.SUMMARIZED


def test_summarize_run_fails_when_cost_cap_is_exceeded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = _prepare_database(tmp_path, monkeypatch)
    settings = load_runtime_settings().model_copy(update={"llm_cost_cap_usd": 1.0})
    run = _prepare_run(database_path)

    monkeypatch.setattr(
        "agent.summarization.service.load_summarization_provider",
        lambda _provider, _model: ExpensiveProvider(),
    )

    try:
        summarize_run(
            settings=settings,
            database_path=database_path,
            product=load_product_catalog(Path.cwd() / "products.yaml").get_product("indmoney"),
            run=run,
        )
    except PulseCostExceeded:
        pass
    else:
        raise AssertionError("Expected summarize_run to raise PulseCostExceeded")

    stored_run = fetch_run(database_path, run.run_id)
    assert stored_run.status == RunStatus.FAILED


def _prepare_database(tmp_path: Path, monkeypatch) -> Path:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    initialize_database(database_path)
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    sync_products(database_path, catalog)
    return database_path


def _prepare_run(database_path: Path):
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    upsert_reviews(database_path, seed_reviews())
    replace_clusters_for_run(database_path, run.run_id, [build_cluster()])
    return run


def _usage(*, cost_usd: float) -> LLMUsage:
    return LLMUsage(
        provider="fake",
        model="fake-v1",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=cost_usd,
        retries=0,
    )
