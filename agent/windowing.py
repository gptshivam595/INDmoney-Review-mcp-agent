from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

ISO_WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")


class ReviewWindow(BaseModel):
    iso_week: str
    timezone: str
    week_start: date
    week_end: date
    window_start: date
    window_end: date
    review_weeks: int = Field(ge=8, le=12)


def normalize_product_key(product_key: str) -> str:
    normalized = product_key.strip().lower().replace(" ", "-").replace("_", "-")
    if not normalized:
        msg = "product_key must not be empty"
        raise ValueError(msg)
    return normalized


def parse_iso_week(iso_week: str) -> tuple[int, int]:
    match = ISO_WEEK_RE.match(iso_week)
    if match is None:
        msg = f"Invalid ISO week: {iso_week}"
        raise ValueError(msg)
    year = int(match.group("year"))
    week = int(match.group("week"))
    if not 1 <= week <= 53:
        msg = f"Invalid ISO week number: {iso_week}"
        raise ValueError(msg)
    return year, week


def resolve_iso_week_start(iso_week: str) -> date:
    year, week = parse_iso_week(iso_week)
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        msg = f"Invalid ISO week: {iso_week}"
        raise ValueError(msg) from exc


def current_iso_week(timezone_name: str) -> str:
    now = datetime.now(ZoneInfo(timezone_name))
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def build_report_anchor(product_key: str, iso_week: str) -> str:
    return f"pulse-{normalize_product_key(product_key)}-{iso_week}"


def build_run_id(product_key: str, iso_week: str) -> str:
    seed = f"{normalize_product_key(product_key)}:{iso_week}".encode()
    return hashlib.sha1(seed).hexdigest()


def build_review_window(iso_week: str, review_weeks: int, timezone_name: str) -> ReviewWindow:
    if not 8 <= review_weeks <= 12:
        msg = "review_weeks must be between 8 and 12"
        raise ValueError(msg)

    week_start = resolve_iso_week_start(iso_week)
    week_end = week_start + timedelta(days=6)
    window_start = week_end - timedelta(days=(review_weeks * 7) - 1)
    return ReviewWindow(
        iso_week=iso_week,
        timezone=timezone_name,
        week_start=week_start,
        week_end=week_end,
        window_start=window_start,
        window_end=week_end,
        review_weeks=review_weeks,
    )
