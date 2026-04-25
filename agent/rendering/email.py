from __future__ import annotations

from html import escape

from agent.config import ProductConfig
from agent.models import EmailRenderPayload, PulseReport

DOC_LINK_PLACEHOLDER = "{{DOC_SECTION_LINK}}"


def render_email_payload(
    report: PulseReport,
    product: ProductConfig,
    *,
    doc_link: str = DOC_LINK_PLACEHOLDER,
) -> EmailRenderPayload:
    subject = f"{report.product_name} Weekly Review Pulse - {report.iso_week}"
    teaser_themes = report.top_themes[:2]
    teaser_lines = [f"- {theme.name}: {theme.summary}" for theme in teaser_themes]
    teaser_body = "\n".join(teaser_lines)
    period = f"{report.window_start.isoformat()} to {report.window_end.isoformat()}"
    text_body = (
        f"{report.product_name} weekly review pulse for {report.iso_week}\n"
        f"Period: {period}\n\n"
        "Top themes:\n"
        f"{teaser_body}\n\n"
        f"Read full report: {doc_link}\n"
        f"Run id: {report.run_id}\n"
        f"Run anchor: {report.report_anchor}\n"
    )
    html_body = _render_email_html(
        report=report,
        subject=subject,
        period=period,
        teaser_lines=teaser_lines,
        doc_link=doc_link,
    )
    return EmailRenderPayload(
        subject=subject,
        to=product.stakeholders.to,
        cc=product.stakeholders.cc,
        bcc=product.stakeholders.bcc,
        doc_link_placeholder=doc_link,
        html_body=html_body,
        text_body=text_body,
    )


def _render_email_html(
    *,
    report: PulseReport,
    subject: str,
    period: str,
    teaser_lines: list[str],
    doc_link: str,
) -> str:
    escaped_theme_items = "".join(
        f"<li>{escape(teaser_line[2:])}</li>"
        for teaser_line in teaser_lines
    )
    return (
        "<html><body>"
        f"<h1>{escape(subject)}</h1>"
        f"<p><strong>Period:</strong> {escape(period)}</p>"
        "<p><strong>Top themes:</strong></p>"
        f"<ul>{escaped_theme_items}</ul>"
        f"<p><a href=\"{escape(doc_link)}\">Read full report</a></p>"
        f"<p><strong>Run id:</strong> {escape(report.run_id)}</p>"
        f"<p><strong>Run anchor:</strong> {escape(report.report_anchor)}</p>"
        "</body></html>"
    )
