from __future__ import annotations

from datetime import datetime

from agent.analysis.preprocess import looks_like_english, preprocess_reviews
from agent.models import RawReview


def make_review(review_id: str, body_scrubbed: str, locale: str | None = None) -> RawReview:
    return RawReview(
        review_id=review_id,
        product_key="indmoney",
        source="fixture",
        external_id=review_id,
        rating=3,
        title=None,
        body_raw=body_scrubbed,
        body_scrubbed=body_scrubbed,
        reviewed_at=datetime.fromisoformat("2026-04-20T10:00:00+00:00"),
        locale=locale,
        raw_payload={"review_id": review_id},
    )


def test_preprocess_reviews_filters_short_and_non_english_reviews() -> None:
    reviews = [
        make_review("eligible", "Application crashes during login and freezes at market open."),
        make_review("short", "Too slow"),
        make_review("non-english", "बिल्कुल काम नहीं करता है"),
    ]

    eligible, filtered = preprocess_reviews(reviews, min_review_length=20)

    assert len(eligible) == 1
    assert filtered == 2
    assert eligible[0].review.review_id == "eligible"


def test_looks_like_english_accepts_explicit_english_locale() -> None:
    assert looks_like_english("en-US", "नमस्ते") is True
