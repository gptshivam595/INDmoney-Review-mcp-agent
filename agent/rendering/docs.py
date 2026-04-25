from __future__ import annotations

from agent.models import DocsAppendPayload, DocsContentBlock, PulseReport


def build_docs_heading(report: PulseReport) -> str:
    return (
        f"{report.product_name} - Weekly Review Pulse - "
        f"{report.iso_week} - {report.report_anchor}"
    )


def render_docs_payload(report: PulseReport) -> DocsAppendPayload:
    _validate_report_for_rendering(report)

    blocks: list[DocsContentBlock] = [
        DocsContentBlock(kind="heading", level=1, text=build_docs_heading(report)),
        DocsContentBlock(
            kind="paragraph",
            text=(
                f"Period covered: {report.window_start.isoformat()} "
                f"to {report.window_end.isoformat()}"
            ),
        ),
        DocsContentBlock(kind="heading", level=2, text="Top themes"),
    ]

    for index, theme in enumerate(report.top_themes, start=1):
        blocks.extend(
            [
                DocsContentBlock(
                    kind="heading",
                    level=3,
                    text=f"{index}. {theme.name}",
                ),
                DocsContentBlock(kind="paragraph", text=theme.summary),
                DocsContentBlock(
                    kind="paragraph",
                    text=f"Sentiment: {theme.sentiment} | Reviews: {theme.review_count}",
                ),
            ]
        )
        if theme.quotes:
            blocks.append(DocsContentBlock(kind="heading", level=4, text="Theme quotes"))
            blocks.append(DocsContentBlock(kind="bullet_list", items=theme.quotes))
        if theme.action_ideas:
            blocks.append(DocsContentBlock(kind="heading", level=4, text="Theme actions"))
            blocks.append(DocsContentBlock(kind="bullet_list", items=theme.action_ideas))

    blocks.extend(
        [
            DocsContentBlock(kind="heading", level=2, text="Representative quotes"),
            DocsContentBlock(kind="bullet_list", items=report.quotes),
            DocsContentBlock(kind="heading", level=2, text="Action ideas"),
            DocsContentBlock(kind="bullet_list", items=report.action_ideas),
            DocsContentBlock(kind="heading", level=2, text="Who this helps"),
            DocsContentBlock(kind="bullet_list", items=report.who_this_helps),
            DocsContentBlock(kind="heading", level=2, text="Run metadata"),
            DocsContentBlock(kind="paragraph", text=f"Run id: {report.run_id}"),
            DocsContentBlock(kind="paragraph", text=f"Product key: {report.product_key}"),
        ]
    )

    return DocsAppendPayload(
        document_title=f"Weekly Review Pulse - {report.product_name}",
        section_anchor=report.report_anchor,
        heading=build_docs_heading(report),
        blocks=blocks,
    )


def _validate_report_for_rendering(report: PulseReport) -> None:
    if not report.report_anchor.strip():
        msg = "PulseReport requires a non-empty report_anchor for rendering"
        raise ValueError(msg)
    if not report.top_themes:
        msg = "PulseReport requires at least one theme for rendering"
        raise ValueError(msg)
    if not report.quotes:
        msg = "PulseReport requires at least one quote for rendering"
        raise ValueError(msg)
