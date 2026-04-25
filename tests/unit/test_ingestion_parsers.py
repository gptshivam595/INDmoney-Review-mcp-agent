from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from agent.config import load_product_catalog
from agent.ingestion.appstore import parse_appstore_payload
from agent.ingestion.playstore import normalize_playstore_reviews


def test_parse_appstore_payload_filters_old_reviews_and_scrubs_pii() -> None:
    payload = json.loads(
        (Path.cwd() / "tests/fixtures/appstore_reviews_page1.json").read_text(encoding="utf-8")
    )
    product = load_product_catalog(Path.cwd() / "products.yaml").get_product("indmoney")

    reviews = parse_appstore_payload(product, payload, since_date=date(2026, 2, 16))

    assert len(reviews) == 1
    assert reviews[0].source == "appstore"
    assert "[REDACTED_EMAIL]" in reviews[0].body_scrubbed
    assert "[REDACTED_PHONE]" in reviews[0].body_scrubbed


def test_normalize_playstore_reviews_filters_old_reviews_and_scrubs_pii() -> None:
    payload = json.loads(
        (Path.cwd() / "tests/fixtures/playstore_reviews_page1.json").read_text(encoding="utf-8")
    )
    product = load_product_catalog(Path.cwd() / "products.yaml").get_product("indmoney")

    reviews = normalize_playstore_reviews(
        product,
        payload,
        since_date=date(2026, 2, 16),
    )

    assert len(reviews) == 1
    assert reviews[0].source == "playstore"
    assert "[REDACTED_AADHAAR]" in reviews[0].body_scrubbed
