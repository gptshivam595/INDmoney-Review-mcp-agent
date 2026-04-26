from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import TypeVar

from agent.analysis.service import analyze_run
from agent.config import ProductCatalog, ProductConfig, RuntimeSettings
from agent.ingestion.service import ReviewFetcher, ingest_reviews_for_run
from agent.mcp.docs_client import DocsMCPClient, DocsMCPTransportError
from agent.mcp.docs_service import publish_docs_run
from agent.mcp.gmail_client import GmailMCPClient, GmailMCPTransportError
from agent.mcp.gmail_service import publish_gmail_run
from agent.models import PipelinePhaseResult, PipelineRunResult, RunRecord
from agent.rendering.service import render_run
from agent.storage import (
    create_or_get_run,
    fetch_analysis_result,
    fetch_docs_publish_result,
    fetch_gmail_publish_result,
    fetch_ingestion_result,
    fetch_render_result,
    fetch_run,
    fetch_summarization_result,
    initialize_database,
    sync_products,
    update_run_orchestration_result,
)
from agent.summarization.service import summarize_run
from agent.windowing import build_review_window, current_iso_week

T = TypeVar("T")


@dataclass(frozen=True)
class PipelineDependencies:
    appstore_fetcher: ReviewFetcher | None = None
    playstore_fetcher: ReviewFetcher | None = None
    docs_client: DocsMCPClient | None = None
    gmail_client: GmailMCPClient | None = None


def ensure_pipeline_run(
    *,
    settings: RuntimeSettings,
    catalog: ProductCatalog,
    product_key: str,
    iso_week: str | None,
    review_weeks: int | None = None,
) -> tuple[Path, ProductConfig, RunRecord]:
    product = catalog.get_product(product_key)
    resolved_iso_week = iso_week or current_iso_week(settings.timezone)
    window = build_review_window(
        iso_week=resolved_iso_week,
        review_weeks=review_weeks or settings.default_review_window_weeks,
        timezone_name=settings.timezone,
    )
    database_path = settings.resolve_database_path()
    initialize_database(database_path)
    sync_products(database_path, catalog)
    run = create_or_get_run(database_path, product.product_key, window)
    return database_path, product, run


def run_product_pipeline(
    *,
    settings: RuntimeSettings,
    catalog: ProductCatalog,
    product_key: str,
    iso_week: str | None = None,
    review_weeks: int | None = None,
    draft_only: bool = False,
    force_gmail_delivery: bool = False,
    dependencies: PipelineDependencies | None = None,
) -> PipelineRunResult:
    database_path, product, run = ensure_pipeline_run(
        settings=settings,
        catalog=catalog,
        product_key=product_key,
        iso_week=iso_week,
        review_weeks=review_weeks,
    )
    active_dependencies = dependencies or PipelineDependencies()
    initial_status = run.status.value
    phase_results: list[PipelinePhaseResult] = []
    pipeline_started = perf_counter()
    error_message: str | None = None

    try:
        _maybe_run_phase(
            phase_results=phase_results,
            phase_name="ingest",
            existing_result=fetch_ingestion_result(database_path, run.run_id),
            execute=lambda: ingest_reviews_for_run(
                settings=settings,
                database_path=database_path,
                product=product,
                run=run,
                appstore_fetcher=active_dependencies.appstore_fetcher,
                playstore_fetcher=active_dependencies.playstore_fetcher,
            ),
        )
        _maybe_run_phase(
            phase_results=phase_results,
            phase_name="analyze",
            existing_result=fetch_analysis_result(database_path, run.run_id),
            execute=lambda: analyze_run(
                settings=settings,
                database_path=database_path,
                run=run,
            ),
        )
        _maybe_run_phase(
            phase_results=phase_results,
            phase_name="summarize",
            existing_result=fetch_summarization_result(database_path, run.run_id),
            execute=lambda: summarize_run(
                settings=settings,
                database_path=database_path,
                product=product,
                run=run,
            ),
        )
        _maybe_run_phase(
            phase_results=phase_results,
            phase_name="render",
            existing_result=fetch_render_result(database_path, run.run_id),
            execute=lambda: render_run(
                settings=settings,
                database_path=database_path,
                product=product,
                run=run,
            ),
        )
        _maybe_run_phase(
            phase_results=phase_results,
            phase_name="publish-docs",
            existing_result=fetch_docs_publish_result(database_path, run.run_id),
            execute=lambda: _execute_with_retry(
                settings=settings,
                phase_name="publish-docs",
                execute=lambda: publish_docs_run(
                    settings=settings,
                    database_path=database_path,
                    product=product,
                    run=run,
                    client=active_dependencies.docs_client,
                ),
                transient_exceptions=(DocsMCPTransportError,),
            ),
        )
        _maybe_run_phase(
            phase_results=phase_results,
            phase_name="publish-gmail",
            existing_result=_gmail_checkpoint_for_request(
                existing_result=fetch_gmail_publish_result(database_path, run.run_id),
                settings=settings,
                draft_only=draft_only,
                force_gmail_delivery=force_gmail_delivery,
            ),
            execute=lambda: _execute_with_retry(
                settings=settings,
                phase_name="publish-gmail",
                execute=lambda: publish_gmail_run(
                    settings=settings,
                    database_path=database_path,
                    product=product,
                    run=run,
                    draft_only=draft_only,
                    force_delivery=force_gmail_delivery,
                    client=active_dependencies.gmail_client,
                ),
                transient_exceptions=(GmailMCPTransportError,),
            ),
        )
    except Exception as exc:
        error_message = str(exc)

    final_run = fetch_run(database_path, run.run_id)
    llm_usage = fetch_summarization_result(database_path, run.run_id)
    result = PipelineRunResult(
        run_id=run.run_id,
        product_key=run.product_key,
        iso_week=run.iso_week,
        initial_status=initial_status,
        final_status=final_run.status.value,
        draft_only=draft_only or not settings.confirm_send,
        resumed=_was_resumed(initial_status, phase_results),
        phase_results=phase_results,
        total_duration_seconds=perf_counter() - pipeline_started,
        llm_total_tokens=llm_usage.usage.total_tokens if llm_usage is not None else 0,
        llm_cost_usd=llm_usage.usage.cost_usd if llm_usage is not None else 0.0,
        error_message=error_message,
    )
    update_run_orchestration_result(database_path, run.run_id, result)
    if error_message is not None:
        msg = error_message
        raise RuntimeError(msg)
    return result


def run_active_product_schedule(
    *,
    settings: RuntimeSettings,
    catalog: ProductCatalog,
    iso_week: str | None = None,
    draft_only: bool = False,
    dependencies_by_product: dict[str, PipelineDependencies] | None = None,
) -> list[PipelineRunResult]:
    results: list[PipelineRunResult] = []
    dependency_lookup = dependencies_by_product or {}
    for product in catalog.products:
        if not product.active:
            continue
        results.append(
            run_product_pipeline(
                settings=settings,
                catalog=catalog,
                product_key=product.product_key,
                iso_week=iso_week,
                draft_only=draft_only,
                dependencies=dependency_lookup.get(product.product_key),
            )
        )
    return results


def _gmail_checkpoint_for_request(
    *,
    existing_result,
    settings: RuntimeSettings,
    draft_only: bool,
    force_gmail_delivery: bool,
):
    if existing_result is None:
        return None
    if force_gmail_delivery:
        return None
    effective_draft_only = draft_only or not settings.confirm_send
    has_unsent_draft = bool(existing_result.gmail_draft_id and not existing_result.gmail_message_id)
    if has_unsent_draft and not effective_draft_only:
        return None
    return existing_result


def _maybe_run_phase(
    *,
    phase_results: list[PipelinePhaseResult],
    phase_name: str,
    existing_result: object | None,
    execute: Callable[[], object],
) -> None:
    if existing_result is not None:
        phase_results.append(
            PipelinePhaseResult(
                phase=phase_name,
                status="skipped",
                attempts=1,
                duration_seconds=0.0,
            )
        )
        return

    started = perf_counter()
    outcome = execute()
    duration = perf_counter() - started
    attempts = 1
    detail = None
    if isinstance(outcome, tuple):
        result, attempts = outcome
        detail = getattr(result, "delivery_status", None)
    else:
        detail = getattr(outcome, "delivery_status", None)
    phase_results.append(
        PipelinePhaseResult(
            phase=phase_name,
            status="executed",
            attempts=attempts,
            duration_seconds=duration,
            detail=detail,
        )
    )


def _execute_with_retry(
    *,
    settings: RuntimeSettings,
    phase_name: str,
    execute: Callable[[], T],
    transient_exceptions: tuple[type[Exception], ...],
) -> tuple[T, int]:
    attempts = settings.orchestration_retry_attempts
    for attempt in range(1, attempts + 1):
        try:
            result = execute()
        except transient_exceptions:
            if attempt >= attempts:
                raise
            if settings.orchestration_retry_backoff_seconds > 0:
                sleep(settings.orchestration_retry_backoff_seconds)
            continue
        return result, attempt

    msg = f"{phase_name} exceeded retry budget"
    raise RuntimeError(msg)


def _was_resumed(initial_status: str, phase_results: list[PipelinePhaseResult]) -> bool:
    if initial_status != "planned":
        return True
    return any(phase.status == "skipped" for phase in phase_results)
