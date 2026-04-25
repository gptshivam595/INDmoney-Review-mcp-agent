from datetime import date

import pytest

from agent.config import ProductConfig
from agent.models import PulseReport, Theme
from agent.rendering.docs import render_docs_payload
from agent.rendering.email import DOC_LINK_PLACEHOLDER, render_email_payload


def test_render_docs_payload_includes_heading_anchor_and_sections() -> None:
    report = make_report()

    payload = render_docs_payload(report)

    assert payload.section_anchor == "pulse-indmoney-2026-W17"
    assert payload.heading == "INDMoney - Weekly Review Pulse - 2026-W17 - pulse-indmoney-2026-W17"
    assert [block.text for block in payload.blocks if block.kind == "heading"][:4] == [
        "INDMoney - Weekly Review Pulse - 2026-W17 - pulse-indmoney-2026-W17",
        "Top themes",
        "1. App performance & reliability",
        "Theme quotes",
    ]


def test_render_email_payload_escapes_html_and_uses_placeholder() -> None:
    report = make_report()
    report.top_themes[0].name = "App <stability> & login"
    report.top_themes[0].summary = "Customers say login <breaks> & stalls."

    payload = render_email_payload(report, make_product())

    assert payload.doc_link_placeholder == DOC_LINK_PLACEHOLDER
    assert "href=\"{{DOC_SECTION_LINK}}\"" in payload.html_body
    assert "App &lt;stability&gt; &amp; login" in payload.html_body
    assert "Read full report: {{DOC_SECTION_LINK}}" in payload.text_body


def test_render_docs_payload_rejects_missing_anchor() -> None:
    report = make_report()
    report.report_anchor = ""

    with pytest.raises(ValueError):
        render_docs_payload(report)


def make_report() -> PulseReport:
    return PulseReport(
        run_id="run-123",
        product_key="indmoney",
        product_name="INDMoney",
        iso_week="2026-W17",
        window_start=date(2026, 2, 16),
        window_end=date(2026, 4, 26),
        top_themes=[
            Theme(
                name="App performance & reliability",
                summary="Customers report crashes during login and market open.",
                review_count=3,
                sentiment="negative",
                quotes=["App crashes during login and market open."],
                action_ideas=["Stabilize login reliability during peak load."],
            )
        ],
        quotes=["App crashes during login and market open."],
        action_ideas=["Stabilize login reliability during peak load."],
        who_this_helps=["Product: prioritize stability fixes."],
        report_anchor="pulse-indmoney-2026-W17",
    )


def make_product() -> ProductConfig:
    return ProductConfig(
        product_key="indmoney",
        display_name="INDMoney",
        appstore_app_id="1",
        playstore_package="com.example.indmoney",
        country_code="IN",
        stakeholders={
            "to": ["team@example.com"],
            "cc": [],
            "bcc": [],
        },
    )
