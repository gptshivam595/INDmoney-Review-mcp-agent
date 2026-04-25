from __future__ import annotations

from pathlib import Path

from agent.config import ProductConfig, RuntimeSettings
from agent.models import (
    AnalysisCluster,
    LLMUsage,
    PulseReport,
    RunRecord,
    RunStatus,
    SummarizationResult,
    Theme,
)
from agent.storage import (
    fetch_clusters_for_run,
    fetch_reviews_for_run,
    update_run_status,
    update_run_summarization_result,
    upsert_report,
)
from agent.summarization.provider import (
    ProviderResponse,
    ThemeSuggestion,
    load_summarization_provider,
)
from agent.summarization.quote_validation import validate_quotes


class PulseCostExceeded(RuntimeError):
    """Raised when summarization usage exceeds the configured cap."""


def summarize_run(
    *,
    settings: RuntimeSettings,
    database_path: Path,
    product: ProductConfig,
    run: RunRecord,
) -> SummarizationResult:
    update_run_status(database_path, run.run_id, RunStatus.SUMMARIZING)
    try:
        reviews = fetch_reviews_for_run(database_path, run)
        review_lookup = {review.review_id: review for review in reviews}
        clusters = fetch_clusters_for_run(database_path, run.run_id)
        if not clusters:
            msg = "No clusters available for summarization"
            raise RuntimeError(msg)

        provider = load_summarization_provider(
            settings.llm_provider,
            settings.llm_model,
            settings.llm_timeout_seconds,
        )
        usage = LLMUsage(provider=settings.llm_provider, model=settings.llm_model)
        top_themes: list[Theme] = []
        all_quotes: list[str] = []
        all_actions: list[str] = []

        for cluster in _rank_clusters(clusters)[:3]:
            cluster_reviews = [
                review_lookup[review_id]
                for review_id in cluster.review_ids
                if review_id in review_lookup
            ]
            if not cluster_reviews:
                continue

            theme_response = provider.label_theme(cluster, cluster_reviews)
            _merge_usage(usage, theme_response)
            suggestion = _coerce_theme_suggestion(theme_response)

            quotes_response = provider.select_quotes(cluster, cluster_reviews)
            _merge_usage(usage, quotes_response)
            candidate_quotes = _coerce_quotes(quotes_response)
            valid_quotes, invalid_quotes = validate_quotes(
                candidate_quotes,
                [review.body_scrubbed for review in cluster_reviews],
            )
            if invalid_quotes and settings.llm_max_retries > 0:
                usage.retries += 1
                repair_response = provider.select_quotes(
                    cluster,
                    cluster_reviews,
                    invalid_quotes=invalid_quotes,
                )
                _merge_usage(usage, repair_response)
                repaired_valid, still_invalid = validate_quotes(
                    _coerce_quotes(repair_response),
                    [review.body_scrubbed for review in cluster_reviews],
                )
                valid_quotes = repaired_valid
                invalid_quotes = still_invalid
            if invalid_quotes:
                msg = f"Quote validation failed for cluster {cluster.cluster_id}"
                raise RuntimeError(msg)

            actions_response = provider.generate_action_ideas(suggestion)
            _merge_usage(usage, actions_response)
            action_ideas = _coerce_actions(actions_response)

            theme = Theme(
                name=suggestion.name,
                summary=suggestion.summary,
                review_count=cluster.review_count,
                sentiment=suggestion.sentiment,
                quotes=valid_quotes,
                action_ideas=action_ideas,
            )
            top_themes.append(theme)
            all_quotes.extend(valid_quotes)
            all_actions.extend(action_ideas)
            _enforce_cost_cap(settings, usage)

        if not top_themes:
            msg = "No valid themes were produced during summarization"
            raise RuntimeError(msg)
        if not all_quotes:
            msg = "No valid quotes were produced during summarization"
            raise RuntimeError(msg)

        report = PulseReport(
            run_id=run.run_id,
            product_key=run.product_key,
            product_name=product.display_name,
            iso_week=run.iso_week,
            window_start=run.window_start,
            window_end=run.window_end,
            top_themes=top_themes,
            quotes=all_quotes,
            action_ideas=all_actions,
            who_this_helps=[
                "Product: prioritize roadmap work from recurring customer themes.",
                "Support: identify repeat complaint patterns that need workflow fixes.",
                "Leadership: review a concise weekly health snapshot grounded in customer voice.",
            ],
            report_anchor=run.report_anchor,
        )
        summary_path = _write_summary_artifact(
            base_directory=settings.resolve_database_path().parent / "summaries",
            run_id=run.run_id,
            report=report,
        )
        upsert_report(database_path, run.run_id, report, summary_path)
        result = SummarizationResult(
            run_id=run.run_id,
            product_key=run.product_key,
            iso_week=run.iso_week,
            summary_path=str(summary_path),
            usage=usage,
            report=report,
        )
        update_run_summarization_result(database_path, run.run_id, result)
        return result
    except Exception as exc:
        update_run_status(database_path, run.run_id, RunStatus.FAILED, error_message=str(exc))
        raise


def _rank_clusters(clusters: list[AnalysisCluster]) -> list[AnalysisCluster]:
    return sorted(
        clusters,
        key=lambda cluster: (
            -(cluster.review_count * max(abs(cluster.sentiment_score), 1.0)),
            cluster.cluster_index,
        ),
    )


def _merge_usage(usage: LLMUsage, response: ProviderResponse) -> None:
    usage.prompt_tokens += response.usage.prompt_tokens
    usage.completion_tokens += response.usage.completion_tokens
    usage.total_tokens += response.usage.total_tokens
    usage.cost_usd += response.usage.cost_usd


def _coerce_theme_suggestion(response: ProviderResponse) -> ThemeSuggestion:
    payload = response.payload
    if not isinstance(payload, ThemeSuggestion):
        msg = "Theme suggestion payload is invalid"
        raise TypeError(msg)
    return payload


def _coerce_quotes(response: ProviderResponse) -> list[str]:
    payload = response.payload
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        msg = "Quote payload is invalid"
        raise TypeError(msg)
    return payload


def _coerce_actions(response: ProviderResponse) -> list[str]:
    payload = response.payload
    if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
        msg = "Action payload is invalid"
        raise TypeError(msg)
    return payload


def _enforce_cost_cap(settings: RuntimeSettings, usage: LLMUsage) -> None:
    if usage.cost_usd > settings.llm_cost_cap_usd:
        msg = (
            f"Summarization cost {usage.cost_usd:.4f} exceeded cap "
            f"{settings.llm_cost_cap_usd:.4f}"
        )
        raise PulseCostExceeded(msg)


def _write_summary_artifact(
    *,
    base_directory: Path,
    run_id: str,
    report: PulseReport,
) -> Path:
    base_directory.mkdir(parents=True, exist_ok=True)
    summary_path = base_directory / f"{run_id}.json"
    summary_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return summary_path
