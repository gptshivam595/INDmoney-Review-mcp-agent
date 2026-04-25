from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer
from google_auth_oauthlib.flow import InstalledAppFlow

from agent.analysis.service import analyze_run
from agent.config import (
    ProductCatalog,
    ProductConfig,
    RuntimeSettings,
    load_product_catalog,
    load_runtime_settings,
)
from agent.ingestion.service import ingest_reviews_for_run
from agent.logging import bind_log_context, clear_log_context, configure_logging, get_logger
from agent.mcp.docs_service import publish_docs_run
from agent.mcp.gmail_service import publish_gmail_run
from agent.models import (
    AnalysisResult,
    DocsPublishResult,
    GmailPublishResult,
    IngestionResult,
    PipelineRunResult,
    RenderResult,
    RunRecord,
    SummarizationResult,
)
from agent.orchestrator import run_active_product_schedule, run_product_pipeline
from agent.rendering.service import render_run
from agent.storage import create_or_get_run, fetch_run, initialize_database, sync_products
from agent.summarization.service import summarize_run
from agent.windowing import build_review_window, current_iso_week

app = typer.Typer(no_args_is_help=True, help="Weekly Product Review Pulse agent CLI.")


def bootstrap_runtime() -> tuple[RuntimeSettings, ProductCatalog]:
    settings = load_runtime_settings()
    configure_logging(settings.log_level)
    catalog = load_product_catalog(settings.resolve_products_path())
    return settings, catalog


def ensure_initialized(settings: RuntimeSettings, catalog: ProductCatalog) -> Path:
    database_path = settings.resolve_database_path()
    initialize_database(database_path)
    sync_products(database_path, catalog)
    return database_path


def ensure_run(
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
    database_path = ensure_initialized(settings, catalog)
    run = create_or_get_run(database_path, product.product_key, window)
    bind_log_context(
        run_id=run.run_id,
        product_key=product.product_key,
        phase="phase-1-ingestion",
    )
    return database_path, product, run


@app.command("init-db")
def init_db() -> None:
    """Initialize the local SQLite database and seed products."""
    settings, catalog = bootstrap_runtime()
    database_path = ensure_initialized(settings, catalog)
    logger = get_logger()
    logger.info(
        "database_initialized",
        database_path=str(database_path),
        products=len(catalog.products),
    )
    typer.echo(f"Initialized database at {database_path}")


@app.command("list-products")
def list_products() -> None:
    """List configured products."""
    _settings, catalog = bootstrap_runtime()
    for product in catalog.products:
        typer.echo(f"{product.product_key}: {product.display_name}")


@app.command("plan-run")
def plan_run(
    product: Annotated[str, typer.Option("--product", help="Configured product key.")],
    week: Annotated[
        str | None,
        typer.Option("--week", help="Target ISO week, e.g. 2026-W17."),
    ] = None,
    weeks: Annotated[
        int | None,
        typer.Option("--weeks", help="Rolling review window in weeks."),
    ] = None,
) -> None:
    """Create or load a deterministic planned run."""
    settings, catalog = bootstrap_runtime()
    _database_path, _product, run = ensure_run(settings, catalog, product, week, weeks)
    typer.echo(run.model_dump_json(indent=2))
    clear_log_context()


def _emit_ingestion_result(result: IngestionResult) -> None:
    typer.echo(result.model_dump_json(indent=2))


def _emit_analysis_result(result: AnalysisResult) -> None:
    typer.echo(result.model_dump_json(indent=2))


def _emit_summarization_result(result: SummarizationResult) -> None:
    typer.echo(result.model_dump_json(indent=2))


def _emit_render_result(result: RenderResult) -> None:
    typer.echo(result.model_dump_json(indent=2))


def _emit_docs_publish_result(result: DocsPublishResult) -> None:
    typer.echo(result.model_dump_json(indent=2))


def _emit_gmail_publish_result(result: GmailPublishResult) -> None:
    typer.echo(result.model_dump_json(indent=2))


def _emit_pipeline_run_result(result: PipelineRunResult) -> None:
    typer.echo(result.model_dump_json(indent=2))


@app.command("ingest")
def ingest(
    product: Annotated[str, typer.Option("--product", help="Configured product key.")],
    week: Annotated[str | None, typer.Option("--week", help="Target ISO week.")] = None,
    weeks: Annotated[
        int | None,
        typer.Option("--weeks", help="Rolling review window in weeks."),
    ] = None,
) -> None:
    """Fetch, scrub, dedupe, and persist reviews for the configured product."""
    settings, catalog = bootstrap_runtime()
    database_path, selected_product, run = ensure_run(settings, catalog, product, week, weeks)
    result = ingest_reviews_for_run(
        settings=settings,
        database_path=database_path,
        product=selected_product,
        run=run,
    )
    _emit_ingestion_result(result)
    clear_log_context()


@app.command("analyze")
def analyze(
    run_id: Annotated[str, typer.Option("--run", help="Existing run id.")],
) -> None:
    """Preprocess, embed, cluster, and rank reviews for an existing run."""
    settings, catalog = bootstrap_runtime()
    database_path = ensure_initialized(settings, catalog)
    run = fetch_run(database_path, run_id)
    bind_log_context(
        run_id=run.run_id,
        product_key=run.product_key,
        phase="phase-2-analysis",
    )
    result = analyze_run(
        settings=settings,
        database_path=database_path,
        run=run,
    )
    _emit_analysis_result(result)
    clear_log_context()


@app.command("summarize")
def summarize(
    run_id: Annotated[str, typer.Option("--run", help="Existing run id.")],
) -> None:
    """Produce a grounded weekly pulse report for an analyzed run."""
    settings, catalog = bootstrap_runtime()
    database_path = ensure_initialized(settings, catalog)
    run = fetch_run(database_path, run_id)
    product = catalog.get_product(run.product_key)
    bind_log_context(
        run_id=run.run_id,
        product_key=run.product_key,
        phase="phase-3-summarization",
    )
    result = summarize_run(
        settings=settings,
        database_path=database_path,
        product=product,
        run=run,
    )
    _emit_summarization_result(result)
    clear_log_context()


@app.command("render")
def render(
    run_id: Annotated[str, typer.Option("--run", help="Existing run id.")],
) -> None:
    """Render publish-ready Docs and email artifacts for a summarized run."""
    settings, catalog = bootstrap_runtime()
    database_path = ensure_initialized(settings, catalog)
    run = fetch_run(database_path, run_id)
    product = catalog.get_product(run.product_key)
    bind_log_context(
        run_id=run.run_id,
        product_key=run.product_key,
        phase="phase-4-rendering",
    )
    result = render_run(
        settings=settings,
        database_path=database_path,
        product=product,
        run=run,
    )
    _emit_render_result(result)
    clear_log_context()


@app.command("publish-docs")
def publish_docs(
    run_id: Annotated[str, typer.Option("--run", help="Existing run id.")],
) -> None:
    """Append the rendered weekly report to the product's running Google Doc."""
    settings, catalog = bootstrap_runtime()
    database_path = ensure_initialized(settings, catalog)
    run = fetch_run(database_path, run_id)
    product = catalog.get_product(run.product_key)
    bind_log_context(
        run_id=run.run_id,
        product_key=run.product_key,
        phase="phase-5-docs-mcp",
    )
    result = publish_docs_run(
        settings=settings,
        database_path=database_path,
        product=product,
        run=run,
    )
    _emit_docs_publish_result(result)
    clear_log_context()


@app.command("publish-gmail")
def publish_gmail(
    run_id: Annotated[str, typer.Option("--run", help="Existing run id.")],
    draft_only: Annotated[
        bool,
        typer.Option("--draft-only", help="Draft instead of send."),
    ] = False,
) -> None:
    """Draft or send the stakeholder email after Docs publish succeeds."""
    settings, catalog = bootstrap_runtime()
    database_path = ensure_initialized(settings, catalog)
    run = fetch_run(database_path, run_id)
    product = catalog.get_product(run.product_key)
    bind_log_context(
        run_id=run.run_id,
        product_key=run.product_key,
        phase="phase-6-gmail-mcp",
    )
    result = publish_gmail_run(
        settings=settings,
        database_path=database_path,
        product=product,
        run=run,
        draft_only=draft_only,
    )
    _emit_gmail_publish_result(result)
    clear_log_context()


@app.command("run")
def run_pipeline(
    product: Annotated[str, typer.Option("--product", help="Configured product key.")],
    week: Annotated[str | None, typer.Option("--week", help="Target ISO week.")] = None,
    weeks: Annotated[
        int | None,
        typer.Option("--weeks", help="Rolling review window in weeks."),
    ] = None,
    draft_only: Annotated[
        bool,
        typer.Option("--draft-only", help="Create a Gmail draft instead of sending."),
    ] = False,
) -> None:
    """Run the full weekly pulse pipeline with checkpoint-aware resume."""
    settings, catalog = bootstrap_runtime()
    result = run_product_pipeline(
        settings=settings,
        catalog=catalog,
        product_key=product,
        iso_week=week,
        review_weeks=weeks,
        draft_only=draft_only,
    )
    _emit_pipeline_run_result(result)
    clear_log_context()


@app.command("run-weekly")
def run_weekly(
    week: Annotated[str | None, typer.Option("--week", help="Target ISO week.")] = None,
    draft_only: Annotated[
        bool,
        typer.Option("--draft-only", help="Create Gmail drafts instead of sending."),
    ] = False,
) -> None:
    """Run the weekly pipeline for every active product."""
    settings, catalog = bootstrap_runtime()
    results = run_active_product_schedule(
        settings=settings,
        catalog=catalog,
        iso_week=week,
        draft_only=draft_only,
    )
    typer.echo(json.dumps([result.model_dump(mode="json") for result in results], indent=2))
    clear_log_context()


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind host.")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", help="Bind port.")] = 8000,
) -> None:
    """Start the operator API and Google helper server."""
    import uvicorn

    uvicorn.run("agent.mcp.server:app", host=host, port=port, reload=False)


@app.command("auth-google")
def auth_google() -> None:
    """Run a local OAuth flow and write an authorized token.json file."""
    client_secret_file = Path(
        os.getenv("GOOGLE_CLIENT_SECRET_FILE") or str(Path.cwd() / "client_secret.json")
    )
    if not client_secret_file.exists():
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise typer.BadParameter(
                "Set GOOGLE_CLIENT_SECRET_FILE or GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first."
            )
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=[
                "https://www.googleapis.com/auth/documents",
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.modify",
            ],
        )
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_file),
            scopes=[
                "https://www.googleapis.com/auth/documents",
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.modify",
            ],
        )
    credentials = flow.run_local_server(port=0)
    output_path = Path(os.getenv("GOOGLE_TOKEN_PATH") or "token.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(credentials.to_json(), encoding="utf-8")
    typer.echo(f"Saved Google token to {output_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
