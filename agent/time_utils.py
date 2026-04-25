from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def next_scheduler_run(
    *,
    now_utc: datetime,
    timezone_name: str,
    day_of_week: int,
    hour_24: int,
    minute: int,
) -> tuple[datetime, datetime]:
    local_zone = ZoneInfo(timezone_name)
    localized_now = now_utc.astimezone(local_zone)
    days_ahead = (day_of_week - localized_now.weekday()) % 7
    candidate_date = localized_now.date() + timedelta(days=days_ahead)
    candidate_local = datetime.combine(
        candidate_date,
        time(hour=hour_24, minute=minute),
        tzinfo=local_zone,
    )
    if candidate_local <= localized_now:
        candidate_local = candidate_local + timedelta(days=7)
    return candidate_local, candidate_local.astimezone(UTC)


def scheduler_summary(
    *,
    enabled: bool,
    timezone_name: str,
    day_of_week: int,
    hour_24: int,
    minute: int,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "enabled": enabled,
        "timezone": timezone_name,
        "day_of_week": day_of_week,
        "day_name": WEEKDAY_NAMES[day_of_week],
        "hour_24": hour_24,
        "minute": minute,
        "cadence_label": f"{WEEKDAY_NAMES[day_of_week]} {hour_24:02d}:{minute:02d}",
    }
    if not enabled:
        summary["next_run_local"] = None
        summary["next_run_utc"] = None
        summary["status"] = "inactive"
        return summary

    reference = now_utc or datetime.now(UTC)
    next_local, next_utc = next_scheduler_run(
        now_utc=reference,
        timezone_name=timezone_name,
        day_of_week=day_of_week,
        hour_24=hour_24,
        minute=minute,
    )
    summary["next_run_local"] = next_local.isoformat()
    summary["next_run_utc"] = next_utc.isoformat()
    summary["status"] = "active"
    return summary
