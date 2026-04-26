from __future__ import annotations

import csv
import hashlib
import re
from datetime import UTC, datetime
from io import StringIO

from agent.ingestion.common import build_review_id, normalize_text, parse_review_datetime
from agent.models import RawReview

TEXT_COLUMNS = ("body", "review", "review_text", "text", "comment", "content", "feedback")
TITLE_COLUMNS = ("title", "subject", "summary")
RATING_COLUMNS = ("rating", "stars", "score", "star_rating")
DATE_COLUMNS = ("reviewed_at", "review_date", "date", "created_at", "timestamp")
ID_COLUMNS = ("review_id", "id", "external_id")
LOCALE_COLUMNS = ("locale", "language")
SOURCE_COLUMNS = ("source", "platform", "store")


def parse_uploaded_csv_reviews(
    *,
    csv_text: str,
    product_key: str,
    upload_id: str,
    fallback_reviewed_at: datetime | None = None,
) -> list[RawReview]:
    normalized_text = csv_text.lstrip("\ufeff").strip()
    if not normalized_text:
        msg = "CSV upload is empty."
        raise ValueError(msg)

    reader = csv.DictReader(StringIO(normalized_text))
    if not reader.fieldnames:
        msg = "CSV upload must include a header row."
        raise ValueError(msg)

    field_lookup = {_normalize_header(field): field for field in reader.fieldnames if field}
    body_field = _find_field(field_lookup, TEXT_COLUMNS)
    if body_field is None:
        expected = ", ".join(TEXT_COLUMNS)
        msg = f"CSV upload must include one review text column, for example: {expected}."
        raise ValueError(msg)

    fallback_date = fallback_reviewed_at or datetime.now(UTC).replace(microsecond=0)
    upload_source = f"csv-upload-{_safe_upload_id(upload_id)}"
    reviews: list[RawReview] = []
    for row_number, row in enumerate(reader, start=1):
        body_raw = normalize_text(row.get(body_field))
        if not body_raw:
            continue

        external_id = _get_first_value(row, field_lookup, ID_COLUMNS)
        if not external_id:
            external_id = hashlib.sha1(
                f"{upload_id}:{row_number}:{body_raw}".encode()
            ).hexdigest()[:16]

        reviewed_at = _parse_optional_datetime(
            _get_first_value(row, field_lookup, DATE_COLUMNS),
            fallback_date,
        )
        original_source = _get_first_value(row, field_lookup, SOURCE_COLUMNS)
        raw_payload = {
            "upload_id": upload_id,
            "row_number": row_number,
            "original_source": original_source,
            "csv_row": dict(row),
        }
        reviews.append(
            RawReview(
                review_id=build_review_id(upload_source, external_id),
                product_key=product_key,
                source=upload_source,
                external_id=external_id,
                rating=_parse_rating(_get_first_value(row, field_lookup, RATING_COLUMNS)),
                title=_optional_text(_get_first_value(row, field_lookup, TITLE_COLUMNS)),
                body_raw=body_raw,
                body_scrubbed=body_raw,
                reviewed_at=reviewed_at,
                locale=_optional_text(_get_first_value(row, field_lookup, LOCALE_COLUMNS)),
                raw_payload=raw_payload,
            )
        )

    if not reviews:
        msg = "CSV upload did not contain any non-empty review text rows."
        raise ValueError(msg)
    return reviews


def _find_field(field_lookup: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        field = field_lookup.get(candidate)
        if field:
            return field
    return None


def _get_first_value(
    row: dict[str, str | None],
    field_lookup: dict[str, str],
    candidates: tuple[str, ...],
) -> str:
    field = _find_field(field_lookup, candidates)
    if field is None:
        return ""
    return normalize_text(row.get(field))


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _optional_text(value: str) -> str | None:
    return value or None


def _parse_rating(value: str) -> int:
    if not value:
        return 3
    try:
        rating = int(round(float(value)))
    except ValueError:
        return 3
    return min(5, max(1, rating))


def _parse_optional_datetime(value: str, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        return parse_review_datetime(value)
    except ValueError:
        pass

    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(value, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
        return parsed
    return fallback


def _safe_upload_id(upload_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", upload_id.lower())[:12] or "manual"
