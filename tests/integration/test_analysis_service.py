from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from agent.analysis.service import analyze_run
from agent.config import load_product_catalog, load_runtime_settings
from agent.models import RawReview
from agent.storage import create_or_get_run, initialize_database, sync_products, upsert_reviews
from agent.windowing import build_review_window


class FakeEmbeddingProvider:
    model_name = "fake-v1"

    def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        if "crash" in lowered or "freeze" in lowered or "login" in lowered:
            return [1.0, 0.0, 0.0]
        if "support" in lowered or "ticket" in lowered or "reply" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


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
        make_review("r4", "Customer support never replies and ticket status stays pending.", 1),
        make_review("r5", "Support team is slow to reply and tickets remain unresolved.", 2),
        make_review("r6", "Ticket updates are poor and support responses take days.", 2),
    ]


def test_analyze_run_clusters_reviews_and_reuses_embedding_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))
    monkeypatch.setenv("PULSE_ANALYSIS_SIMILARITY_THRESHOLD", "0.8")
    monkeypatch.setenv("PULSE_ANALYSIS_MIN_CLUSTER_SIZE", "2")

    initialize_database(database_path)
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    sync_products(database_path, catalog)
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, "indmoney", window)
    upsert_reviews(database_path, seed_reviews())
    settings = load_runtime_settings()

    monkeypatch.setattr(
        "agent.analysis.service.load_embedding_provider",
        lambda _settings: FakeEmbeddingProvider(),
    )

    first = analyze_run(settings=settings, database_path=database_path, run=run)
    second = analyze_run(settings=settings, database_path=database_path, run=run)

    connection = sqlite3.connect(database_path)
    cluster_count = connection.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]

    assert first.clusters_formed == 2
    assert first.embedding_cache_hits == 0
    assert first.embedding_cache_misses == 6
    assert second.embedding_cache_hits == 6
    assert second.embedding_cache_misses == 0
    assert cluster_count == 2
    assert [cluster.review_count for cluster in first.clusters] == [3, 3]
    assert Path(first.artifact_path).exists()
