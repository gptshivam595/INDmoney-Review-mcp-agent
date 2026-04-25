from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any

from agent.config import ProductConfig
from agent.ingestion.common import (
    build_review_id,
    normalize_text,
    parse_review_datetime,
    within_window,
)
from agent.ingestion.scrubber import scrub_pii
from agent.models import RawReview


def normalize_playstore_reviews(
    product: ProductConfig,
    payloads: list[dict[str, Any]],
    since_date: date,
) -> list[RawReview]:
    reviews: list[RawReview] = []
    for payload in payloads:
        external_id = _string_value(payload.get("reviewId"))
        content = normalize_text(_string_value(payload.get("content")))
        reviewed_at_raw = payload.get("at")
        if not external_id or not content or reviewed_at_raw is None:
            continue

        reviewed_at = parse_review_datetime(reviewed_at_raw)
        if not within_window(reviewed_at, since_date):
            continue

        score = int(payload.get("score", 0))
        if score < 1 or score > 5:
            continue

        title = normalize_text(_string_value(payload.get("title"))) or None
        locale = _string_value(payload.get("reviewCreatedVersion")) or None
        reviews.append(
            RawReview(
                review_id=build_review_id("playstore", external_id),
                product_key=product.product_key,
                source="playstore",
                external_id=external_id,
                rating=score,
                title=title,
                body_raw=content,
                body_scrubbed=scrub_pii(content),
                reviewed_at=reviewed_at,
                locale=locale,
                raw_payload=payload,
            )
        )

    return reviews


def fetch_playstore_reviews(
    product: ProductConfig,
    since_date: date,
    page_size: int = 200,
    max_pages: int = 5,
) -> list[RawReview]:
    module: Any = import_module("google_play_scraper")
    review_sort = module.Sort
    reviews_fn = module.reviews
    continuation_token: str | None = None
    all_reviews: list[RawReview] = []

    for _page in range(max_pages):
        payloads, continuation_token = reviews_fn(
            product.playstore_package,
            lang="en",
            country=product.country_code.lower(),
            sort=review_sort.NEWEST,
            count=page_size,
            continuation_token=continuation_token,
        )
        page_reviews = normalize_playstore_reviews(product, payloads, since_date)
        if not page_reviews:
            break
        all_reviews.extend(page_reviews)
        if continuation_token is None:
            break

    return all_reviews


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""
