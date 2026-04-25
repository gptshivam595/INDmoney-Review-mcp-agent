from __future__ import annotations

import re
from dataclasses import dataclass

from agent.ingestion.common import normalize_text
from agent.models import RawReview

ENGLISH_HINT_RE = re.compile(r"[a-zA-Z]")


@dataclass(frozen=True)
class EligibleReview:
    review: RawReview
    normalized_text: str


def preprocess_reviews(
    reviews: list[RawReview],
    *,
    min_review_length: int,
) -> tuple[list[EligibleReview], int]:
    eligible: list[EligibleReview] = []
    filtered = 0

    for review in reviews:
        normalized_text = normalize_text(review.body_scrubbed)
        if len(normalized_text) < min_review_length:
            filtered += 1
            continue
        if not looks_like_english(review.locale, normalized_text):
            filtered += 1
            continue
        eligible.append(EligibleReview(review=review, normalized_text=normalized_text))

    return eligible, filtered


def looks_like_english(locale: str | None, text: str) -> bool:
    if locale and locale.lower().startswith("en"):
        return True
    if not text:
        return False
    english_letters = len(ENGLISH_HINT_RE.findall(text))
    ratio = english_letters / max(len(text), 1)
    return ratio >= 0.45
