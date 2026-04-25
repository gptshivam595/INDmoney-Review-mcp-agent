from agent.windowing import build_report_anchor, build_review_window, build_run_id


def test_build_run_id_is_deterministic() -> None:
    assert build_run_id("INDMoney", "2026-W17") == build_run_id("indmoney", "2026-W17")


def test_build_report_anchor_is_deterministic() -> None:
    assert build_report_anchor("INDMoney", "2026-W17") == "pulse-indmoney-2026-W17"


def test_build_review_window_computes_expected_bounds() -> None:
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")

    assert window.week_start.isoformat() == "2026-04-20"
    assert window.week_end.isoformat() == "2026-04-26"
    assert window.window_start.isoformat() == "2026-02-16"
    assert window.window_end.isoformat() == "2026-04-26"

