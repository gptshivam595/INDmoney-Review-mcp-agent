from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.request import urlopen

from agent.config import ProductConfig
from agent.ingestion.common import (
    build_review_id,
    normalize_text,
    parse_review_datetime,
    within_window,
)
from agent.ingestion.scrubber import scrub_pii
from agent.models import RawReview


def appstore_feed_url(app_id: str, country_code: str, page: int) -> str:
    country = country_code.lower()
    return (
        f"https://itunes.apple.com/{country}/rss/customerreviews/"
        f"page={page}/id={app_id}/sortBy=mostRecent/json"
    )


def parse_appstore_payload(
    product: ProductConfig,
    payload: dict[str, Any],
    since_date: date,
) -> list[RawReview]:
    entries = payload.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []

    reviews: list[RawReview] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if "im:rating" not in entry or "content" not in entry:
            continue

        external_id = _nested_label(entry, "id")
        body_raw = normalize_text(_nested_label(entry, "content"))
        title = normalize_text(_nested_label(entry, "title")) or None
        reviewed_at_value = _nested_label(entry, "updated")
        if not external_id or not body_raw or not reviewed_at_value:
            continue

        reviewed_at = parse_review_datetime(reviewed_at_value)
        if not within_window(reviewed_at, since_date):
            continue

        rating_label = _nested_label(entry, "im:rating")
        if not rating_label:
            continue

        reviews.append(
            RawReview(
                review_id=build_review_id("appstore", external_id),
                product_key=product.product_key,
                source="appstore",
                external_id=external_id,
                rating=int(rating_label),
                title=title,
                body_raw=body_raw,
                body_scrubbed=scrub_pii(body_raw),
                reviewed_at=reviewed_at,
                locale=None,
                raw_payload=entry,
            )
        )

    return reviews


def fetch_appstore_reviews(
    product: ProductConfig,
    since_date: date,
    max_pages: int = 10,
) -> list[RawReview]:
    all_reviews: list[RawReview] = []
    for page in range(1, max_pages + 1):
        url = appstore_feed_url(product.appstore_app_id, product.country_code, page)
        with urlopen(url, timeout=30) as response:  # noqa: S310
            payload = json.load(response)
        page_reviews = parse_appstore_payload(product, payload, since_date)
        if not page_reviews:
            break
        all_reviews.extend(page_reviews)
    return all_reviews


def _nested_label(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        label = value.get("label")
        if isinstance(label, str):
            return label
    elif isinstance(value, str):
        return value
    return ""
