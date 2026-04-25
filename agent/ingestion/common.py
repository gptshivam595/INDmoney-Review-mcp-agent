from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime


def build_review_id(source: str, external_id: str) -> str:
    return hashlib.sha1(f"{source}:{external_id}".encode()).hexdigest()


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split()).strip()


def parse_review_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def within_window(reviewed_at: datetime, since_date: date) -> bool:
    return reviewed_at.date() >= since_date


def serialize_payload(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        default=_json_default,
    )


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
