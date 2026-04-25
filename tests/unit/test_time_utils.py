from datetime import UTC, datetime

from agent.time_utils import next_scheduler_run, scheduler_summary


def test_next_scheduler_run_rolls_forward_to_next_week_when_slot_has_passed() -> None:
    next_local, next_utc = next_scheduler_run(
        now_utc=datetime(2026, 4, 27, 9, 0, tzinfo=UTC),
        timezone_name="Asia/Kolkata",
        day_of_week=0,
        hour_24=9,
        minute=0,
    )

    assert next_local.isoformat() == "2026-05-04T09:00:00+05:30"
    assert next_utc.isoformat() == "2026-05-04T03:30:00+00:00"


def test_scheduler_summary_reports_inactive_when_disabled() -> None:
    summary = scheduler_summary(
        enabled=False,
        timezone_name="Asia/Kolkata",
        day_of_week=0,
        hour_24=9,
        minute=0,
        now_utc=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
    )

    assert summary["status"] == "inactive"
    assert summary["next_run_local"] is None
