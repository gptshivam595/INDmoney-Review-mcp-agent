from __future__ import annotations

from agent.models import AnalysisCluster, RawReview


def build_theme_prompt(cluster: AnalysisCluster, reviews: list[RawReview]) -> str:
    evidence = "\n".join(review.body_scrubbed for review in reviews[:3])
    return (
        "Name the theme represented by these clustered app reviews.\n"
        f"Keyphrases: {', '.join(cluster.keyphrases)}\n"
        f"Representative evidence:\n{evidence}"
    )


def build_quote_prompt(cluster: AnalysisCluster, reviews: list[RawReview]) -> str:
    del cluster
    evidence = "\n".join(review.body_scrubbed for review in reviews)
    return (
        "Select verbatim quotes from the reviews below. "
        "Quotes must appear exactly in the evidence.\n"
        f"Evidence:\n{evidence}"
    )


def build_action_prompt(theme_name: str, summary: str, sentiment: str) -> str:
    return (
        "Generate concise action ideas for the theme below.\n"
        f"Theme: {theme_name}\nSummary: {summary}\nSentiment: {sentiment}"
    )
