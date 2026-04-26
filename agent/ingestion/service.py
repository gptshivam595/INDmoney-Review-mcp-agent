from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

from agent.config import ProductConfig, RuntimeSettings
from agent.ingestion.appstore import fetch_appstore_reviews
from agent.ingestion.common import serialize_payload
from agent.ingestion.playstore import fetch_playstore_reviews
from agent.models import IngestionResult, RawReview, RunRecord, RunStatus
from agent.storage import update_run_ingestion_result, update_run_status, upsert_reviews

ReviewFetcher = Callable[[ProductConfig, date], list[RawReview]]


def ingest_reviews_for_run(
    *,
    settings: RuntimeSettings,
    database_path: Path,
    product: ProductConfig,
    run: RunRecord,
    appstore_fetcher: ReviewFetcher | None = None,
    playstore_fetcher: ReviewFetcher | None = None,
) -> IngestionResult:
    update_run_status(database_path, run.run_id, RunStatus.INGESTING)
    try:
        since_date = run.window_start
        resolved_appstore_fetcher = appstore_fetcher or fetch_appstore_reviews
        resolved_playstore_fetcher = playstore_fetcher or fetch_playstore_reviews
        reviews = _dedupe_reviews(
            resolved_appstore_fetcher(product, since_date)
            + resolved_playstore_fetcher(product, since_date)
        )
        raw_snapshot_path = _write_raw_snapshot(
            base_directory=settings.resolve_database_path().parent / "raw",
            product_key=product.product_key,
            run_id=run.run_id,
            reviews=reviews,
        )
        stats = upsert_reviews(database_path, reviews)
        sources = dict(Counter(review.source for review in reviews))
        result = IngestionResult(
            run_id=run.run_id,
            product_key=run.product_key,
            iso_week=run.iso_week,
            fetched=len(reviews),
            inserted=stats["inserted"],
            updated=stats["updated"],
            unchanged=stats["unchanged"],
            raw_snapshot_path=str(raw_snapshot_path),
            sources=sources,
            review_ids=[review.review_id for review in reviews],
        )
        update_run_ingestion_result(database_path, run.run_id, result)
        return result
    except Exception as exc:
        update_run_status(database_path, run.run_id, RunStatus.FAILED, error_message=str(exc))
        raise


def _dedupe_reviews(reviews: list[RawReview]) -> list[RawReview]:
    deduped: dict[str, RawReview] = {}
    for review in sorted(
        reviews,
        key=lambda item: (item.source, item.reviewed_at.isoformat(), item.external_id),
    ):
        deduped[review.review_id] = review
    return list(deduped.values())


def _write_raw_snapshot(
    *,
    base_directory: Path,
    product_key: str,
    run_id: str,
    reviews: list[RawReview],
) -> Path:
    directory = base_directory / product_key
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_path = directory / f"{run_id}.jsonl"
    with snapshot_path.open("w", encoding="utf-8") as handle:
        for review in reviews:
            line = {
                "review_id": review.review_id,
                "product_key": review.product_key,
                "source": review.source,
                "external_id": review.external_id,
                "reviewed_at": review.reviewed_at.isoformat(),
                "raw_payload": json.loads(serialize_payload(review.raw_payload)),
            }
            handle.write(json.dumps(line, sort_keys=True))
            handle.write("\n")
    return snapshot_path
