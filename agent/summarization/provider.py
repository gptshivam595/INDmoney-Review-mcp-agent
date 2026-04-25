from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.request import Request, urlopen

from agent.models import AnalysisCluster, LLMUsage, RawReview
from agent.summarization.prompts import (
    build_action_prompt,
    build_quote_prompt,
    build_theme_prompt,
)

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


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


@dataclass(frozen=True)
class OpenAISummarizationProvider:
    model_name: str
    api_key: str
    timeout_seconds: int = 30

    def label_theme(self, cluster: AnalysisCluster, reviews: list[RawReview]) -> ProviderResponse:
        payload, usage = self._request_json(
            system_prompt=(
                "You summarize clusters of app reviews into crisp product themes. "
                "Return valid JSON only."
            ),
            user_prompt=(
                f"{build_theme_prompt(cluster, reviews)}\n\n"
                "Return a JSON object with keys: "
                '"name", "summary", and "sentiment". '
                'The "sentiment" must be one of "negative", "mixed", or "positive". '
                'Keep the summary to 1 or 2 short sentences.'
            ),
            temperature=0.2,
        )
        suggestion = ThemeSuggestion(
            name=_json_string(payload, "name"),
            summary=_json_string(payload, "summary"),
            sentiment=_json_choice(payload, "sentiment", {"negative", "mixed", "positive"}),
        )
        return ProviderResponse(usage=usage, payload=suggestion)

    def select_quotes(
        self,
        cluster: AnalysisCluster,
        reviews: list[RawReview],
        invalid_quotes: list[str] | None = None,
    ) -> ProviderResponse:
        retry_block = ""
        if invalid_quotes:
            retry_block = (
                "\nDo not repeat any of these invalid quotes:\n"
                + "\n".join(f"- {quote}" for quote in invalid_quotes)
            )
        payload, usage = self._request_json(
            system_prompt=(
                "You extract exact customer quotes from review evidence. "
                "Return valid JSON only."
            ),
            user_prompt=(
                f"{build_quote_prompt(cluster, reviews)}\n\n"
                "Return a JSON object with a single key named "
                '"quotes". '
                "Its value must be an array with 1 to 3 exact verbatim quotes copied "
                "from the evidence."
                f"{retry_block}"
            ),
            temperature=0.0,
        )
        quotes = _json_string_list(payload, "quotes")
        return ProviderResponse(usage=usage, payload=quotes[:3])

    def generate_action_ideas(self, theme: ThemeSuggestion) -> ProviderResponse:
        payload, usage = self._request_json(
            system_prompt=(
                "You turn app review themes into concise product action ideas. "
                "Return valid JSON only."
            ),
            user_prompt=(
                f"{build_action_prompt(theme.name, theme.summary, theme.sentiment)}\n\n"
                "Return a JSON object with a single key named "
                '"actions". '
                "Its value must be an array with 2 concise action ideas."
            ),
            temperature=0.2,
        )
        actions = _json_string_list(payload, "actions")
        return ProviderResponse(usage=usage, payload=actions[:3])

    def _request_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> tuple[dict[str, object], LLMUsage]:
        body = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
        request = Request(
            OPENAI_CHAT_COMPLETIONS_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            response_payload = json.load(response)
        message = _extract_openai_message_content(response_payload)
        parsed_payload = json.loads(message)
        if not isinstance(parsed_payload, dict):
            msg = "OpenAI summarization response was not a JSON object"
            raise RuntimeError(msg)
        usage = _usage_from_openai(
            provider="openai",
            model=self.model_name,
            usage_payload=response_payload.get("usage", {}),
        )
        return parsed_payload, usage


def load_summarization_provider(
    provider: str,
    model: str,
    timeout_seconds: int = 30,
) -> SummarizationProvider:
    normalized_provider = provider.strip().lower()
    if normalized_provider == "openai":
        api_key = _lookup_env_value("OPENAI_API_KEY")
        if not api_key:
            msg = "OPENAI_API_KEY is required when llm_provider=openai"
            raise RuntimeError(msg)
        resolved_model = model if model and model != "heuristic-v1" else "gpt-4.1-mini"
        return OpenAISummarizationProvider(
            model_name=resolved_model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    return HeuristicSummarizationProvider(provider_name=normalized_provider, model_name=model)


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


def _usage_from_openai(*, provider: str, model: str, usage_payload: object) -> LLMUsage:
    usage = usage_payload if isinstance(usage_payload, dict) else {}
    prompt_tokens = _coerce_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    completion_tokens = _coerce_int(
        usage.get("completion_tokens") or usage.get("output_tokens")
    )
    total_tokens = _coerce_int(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return LLMUsage(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=0.0,
        retries=0,
    )


def _extract_openai_message_content(response_payload: object) -> str:
    if not isinstance(response_payload, dict):
        msg = "OpenAI response payload was invalid"
        raise RuntimeError(msg)
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        msg = "OpenAI response did not include choices"
        raise RuntimeError(msg)
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        msg = "OpenAI response choice payload was invalid"
        raise RuntimeError(msg)
    message = first_choice.get("message")
    if not isinstance(message, dict):
        msg = "OpenAI response did not include a message payload"
        raise RuntimeError(msg)
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        msg = "OpenAI response did not include message content"
        raise RuntimeError(msg)
    return content


def _json_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"Expected non-empty string for '{key}'"
        raise RuntimeError(msg)
    return value.strip()


def _json_choice(payload: dict[str, object], key: str, allowed: set[str]) -> str:
    value = _json_string(payload, key).lower()
    if value not in allowed:
        msg = f"Unexpected value for '{key}': {value}"
        raise RuntimeError(msg)
    return value


def _json_string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        msg = f"Expected list for '{key}'"
        raise RuntimeError(msg)
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if not items:
        msg = f"Expected at least one string item for '{key}'"
        raise RuntimeError(msg)
    return items


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def _lookup_env_value(key: str) -> str | None:
    direct_value = os.getenv(key)
    if direct_value:
        return direct_value

    env_path = os.getcwd()
    dotenv_path = os.path.join(env_path, ".env")
    if not os.path.exists(dotenv_path):
        return None

    with open(dotenv_path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() != key:
                continue
            cleaned = value.strip().strip("'").strip('"')
            return cleaned or None
    return None
