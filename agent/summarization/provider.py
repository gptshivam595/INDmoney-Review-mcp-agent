from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from agent.models import AnalysisCluster, LLMUsage, RawReview
from agent.summarization.prompts import (
    build_action_prompt,
    build_quote_prompt,
    build_theme_prompt,
)


@dataclass(frozen=True)
class ThemeSuggestion:
    name: str
    summary: str
    sentiment: str


@dataclass(frozen=True)
class ProviderResponse:
    usage: LLMUsage
    payload: object


class SummarizationProvider(Protocol):
    def label_theme(self, cluster: AnalysisCluster, reviews: list[RawReview]) -> ProviderResponse:
        ...

    def select_quotes(
        self,
        cluster: AnalysisCluster,
        reviews: list[RawReview],
        invalid_quotes: list[str] | None = None,
    ) -> ProviderResponse:
        ...

    def generate_action_ideas(self, theme: ThemeSuggestion) -> ProviderResponse:
        ...


@dataclass(frozen=True)
class HeuristicSummarizationProvider:
    provider_name: str
    model_name: str

    def label_theme(self, cluster: AnalysisCluster, reviews: list[RawReview]) -> ProviderResponse:
        theme_name = _infer_theme_name(cluster, reviews)
        summary = _infer_summary(cluster, reviews, theme_name)
        sentiment = _sentiment_label(cluster.sentiment_score)
        usage = _usage(
            provider=self.provider_name,
            model=self.model_name,
            prompt_text=build_theme_prompt(cluster, reviews),
            completion_text=f"{theme_name} {summary} {sentiment}",
        )
        return ProviderResponse(
            usage=usage,
            payload=ThemeSuggestion(name=theme_name, summary=summary, sentiment=sentiment),
        )

    def select_quotes(
        self,
        cluster: AnalysisCluster,
        reviews: list[RawReview],
        invalid_quotes: list[str] | None = None,
    ) -> ProviderResponse:
        quotes = [_best_quote(review.body_scrubbed) for review in reviews[:2]]
        if invalid_quotes:
            quotes = [
                _best_quote(review.body_scrubbed, force_full_text=True)
                for review in reviews[:2]
            ]
        usage = _usage(
            provider=self.provider_name,
            model=self.model_name,
            prompt_text=build_quote_prompt(cluster, reviews),
            completion_text=" ".join(quotes),
        )
        return ProviderResponse(usage=usage, payload=[quote for quote in quotes if quote])

    def generate_action_ideas(self, theme: ThemeSuggestion) -> ProviderResponse:
        actions = _infer_actions(theme)
        usage = _usage(
            provider=self.provider_name,
            model=self.model_name,
            prompt_text=build_action_prompt(theme.name, theme.summary, theme.sentiment),
            completion_text=" ".join(actions),
        )
        return ProviderResponse(usage=usage, payload=actions)


def load_summarization_provider(provider: str, model: str) -> SummarizationProvider:
    return HeuristicSummarizationProvider(provider_name=provider, model_name=model)


def _infer_theme_name(cluster: AnalysisCluster, reviews: list[RawReview]) -> str:
    lowered_keyphrases = [phrase.lower() for phrase in cluster.keyphrases]
    text = " ".join(review.body_scrubbed.lower() for review in reviews)
    if any(term in text for term in ["crash", "freeze", "bug", "login", "lag"]):
        return "App performance and reliability"
    if any(term in text for term in ["support", "ticket", "reply", "service"]):
        return "Customer support friction"
    if any(term in text for term in ["portfolio", "navigation", "insight", "ux"]):
        return "UX and feature clarity"
    if lowered_keyphrases:
        lead = ", ".join(cluster.keyphrases[:2])
        return f"Customer feedback around {lead}"
    return "General customer feedback"


def _infer_summary(cluster: AnalysisCluster, reviews: list[RawReview], theme_name: str) -> str:
    evidence = reviews[0].body_scrubbed if reviews else ""
    snippet = evidence[:120].rstrip(" .,;:")
    review_count = cluster.review_count
    return f"{theme_name} appears across {review_count} reviews. Representative signal: {snippet}."


def _sentiment_label(sentiment_score: float) -> str:
    if sentiment_score <= -0.5:
        return "negative"
    if sentiment_score >= 0.5:
        return "positive"
    return "mixed"


def _best_quote(body: str, *, force_full_text: bool = False) -> str:
    normalized = " ".join(body.split()).strip()
    if force_full_text or len(normalized) <= 140:
        return normalized
    for separator in [". ", "! ", "? ", "; "]:
        if separator in normalized:
            candidate = normalized.split(separator, maxsplit=1)[0].strip()
            if len(candidate) >= 20:
                return candidate
    return normalized[:140].rstrip(" ,;:")


def _infer_actions(theme: ThemeSuggestion) -> list[str]:
    lowered = theme.name.lower()
    if "performance" in lowered or "reliability" in lowered:
        return [
            "Stabilize peak-load behavior and improve crash monitoring.",
            "Prioritize login and session recovery fixes.",
        ]
    if "support" in lowered:
        return [
            "Expose clearer ticket status updates inside the app.",
            "Tighten response-time expectations for customer support.",
        ]
    if "ux" in lowered or "feature" in lowered or "clarity" in lowered:
        return [
            "Simplify the navigation path for the affected workflow.",
            "Add clearer in-app guidance for the confusing feature area.",
        ]
    return [
        "Review the cluster evidence and prioritize the recurring customer pain point.",
        "Validate the underlying issue with support and product telemetry.",
    ]


def _usage(*, provider: str, model: str, prompt_text: str, completion_text: str) -> LLMUsage:
    prompt_tokens = max(1, math.ceil(len(prompt_text.split()) * 1.3))
    completion_tokens = max(1, math.ceil(len(completion_text.split()) * 1.3))
    return LLMUsage(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=0.0,
        retries=0,
    )
