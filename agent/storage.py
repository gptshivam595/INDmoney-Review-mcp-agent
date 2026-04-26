from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path

from agent.config import ProductCatalog, ProductConfig
from agent.ingestion.common import serialize_payload
from agent.models import (
    AnalysisCluster,
    AnalysisResult,
    DeliveryEventEntry,
    DeliveryResult,
    DocsPublishResult,
    GmailPublishResult,
    IngestionResult,
    LLMUsage,
    PipelineRunResult,
    PulseReport,
    RawReview,
    RenderResult,
    RunHistoryEntry,
    RunRecord,
    RunStatus,
    SummarizationResult,
)
from agent.windowing import ReviewWindow, build_report_anchor, build_run_id

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    product_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    appstore_app_id TEXT NOT NULL,
    playstore_package TEXT NOT NULL,
    country_code TEXT NOT NULL,
    stakeholders_json TEXT NOT NULL,
    active INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    product_key TEXT NOT NULL,
    iso_week TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    review_weeks INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    summary_path TEXT,
    artifact_dir TEXT,
    gdoc_id TEXT,
    gdoc_section_anchor TEXT NOT NULL,
    gdoc_heading_id TEXT,
    gdoc_deep_link TEXT,
    gmail_draft_id TEXT,
    gmail_message_id TEXT,
    metrics_json TEXT NOT NULL,
    error_json TEXT,
    locked_at TEXT,
    locked_by TEXT,
    UNIQUE(product_key, iso_week)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    product_key TEXT NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    rating INTEGER NOT NULL,
    title TEXT,
    body_raw TEXT NOT NULL,
    body_scrubbed TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    locale TEXT,
    raw_json TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE(product_key, source, external_id)
);

CREATE TABLE IF NOT EXISTS review_embeddings (
    review_id TEXT PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    embedding_sha1 TEXT NOT NULL,
    vector BLOB,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters (
    cluster_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    cluster_index INTEGER NOT NULL,
    review_ids_json TEXT NOT NULL,
    review_count INTEGER NOT NULL,
    representative_review_id TEXT,
    keyphrases_json TEXT NOT NULL DEFAULT '[]',
    noise_flag INTEGER NOT NULL DEFAULT 0,
    sentiment_score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    report_json TEXT NOT NULL,
    artifact_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    external_id TEXT,
    payload_sha1 TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        _migrate_schema(connection)


def sync_products(database_path: Path, catalog: ProductCatalog) -> None:
    with connect(database_path) as connection:
        for product in catalog.products:
            _upsert_product(connection, product)
        connection.commit()


def _upsert_product(connection: sqlite3.Connection, product: ProductConfig) -> None:
    timestamp = utc_now()
    connection.execute(
        """
        INSERT INTO products (
            product_key, display_name, appstore_app_id, playstore_package, country_code,
            stakeholders_json, active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(product_key) DO UPDATE SET
            display_name = excluded.display_name,
            appstore_app_id = excluded.appstore_app_id,
            playstore_package = excluded.playstore_package,
            country_code = excluded.country_code,
            stakeholders_json = excluded.stakeholders_json,
            active = excluded.active,
            updated_at = excluded.updated_at
        """,
        (
            product.product_key,
            product.display_name,
            product.appstore_app_id,
            product.playstore_package,
            product.country_code,
            json.dumps(product.stakeholders.model_dump()),
            int(product.active),
            timestamp,
            timestamp,
        ),
    )


def create_or_get_run(database_path: Path, product_key: str, window: ReviewWindow) -> RunRecord:
    run_id = build_run_id(product_key, window.iso_week)
    anchor = build_report_anchor(product_key, window.iso_week)
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO runs (
                run_id, product_key, iso_week, window_start, window_end, review_weeks,
                status, started_at, gdoc_section_anchor, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                product_key,
                window.iso_week,
                window.window_start.isoformat(),
                window.window_end.isoformat(),
                window.review_weeks,
                RunStatus.PLANNED.value,
                utc_now(),
                anchor,
                json.dumps({"phase": "phase-0-foundations"}),
            ),
        )
        row = connection.execute(
            """
            SELECT
                run_id, product_key, iso_week, status, window_start, window_end, gdoc_section_anchor
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            msg = f"Run not found after insert: {run_id}"
            raise RuntimeError(msg)
        connection.commit()

    return RunRecord(
        run_id=row["run_id"],
        product_key=row["product_key"],
        iso_week=row["iso_week"],
        status=RunStatus(row["status"]),
        window_start=row["window_start"],
        window_end=row["window_end"],
        report_anchor=row["gdoc_section_anchor"],
    )


def fetch_run(database_path: Path, run_id: str) -> RunRecord:
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                run_id, product_key, iso_week, status, window_start, window_end, gdoc_section_anchor
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    if row is None:
        msg = f"Unknown run_id: {run_id}"
        raise KeyError(msg)

    return RunRecord(
        run_id=row["run_id"],
        product_key=row["product_key"],
        iso_week=row["iso_week"],
        status=RunStatus(row["status"]),
        window_start=row["window_start"],
        window_end=row["window_end"],
        report_anchor=row["gdoc_section_anchor"],
    )


def fetch_reviews_for_run(database_path: Path, run: RunRecord) -> list[RawReview]:
    with connect(database_path) as connection:
        review_ids = _load_ingested_review_ids(connection, run.run_id)
        if review_ids:
            placeholders = ", ".join("?" for _ in review_ids)
            rows = connection.execute(
                f"""
                SELECT
                    review_id, product_key, source, external_id, rating, title, body_raw,
                    body_scrubbed, reviewed_at, locale, raw_json
                FROM reviews
                WHERE product_key = ?
                  AND review_id IN ({placeholders})
                ORDER BY reviewed_at DESC, review_id ASC
                """,
                (run.product_key, *review_ids),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT
                    review_id, product_key, source, external_id, rating, title, body_raw,
                    body_scrubbed, reviewed_at, locale, raw_json
                FROM reviews
                WHERE product_key = ?
                  AND reviewed_at >= ?
                  AND reviewed_at <= ?
                ORDER BY reviewed_at DESC, review_id ASC
                """,
                (
                    run.product_key,
                    f"{run.window_start.isoformat()}T00:00:00",
                    f"{run.window_end.isoformat()}T23:59:59.999999+00:00",
                ),
            ).fetchall()

    return [
        RawReview(
            review_id=row["review_id"],
            product_key=row["product_key"],
            source=row["source"],
            external_id=row["external_id"],
            rating=row["rating"],
            title=row["title"],
            body_raw=row["body_raw"],
            body_scrubbed=row["body_scrubbed"],
            reviewed_at=row["reviewed_at"],
            locale=row["locale"],
            raw_payload=json.loads(row["raw_json"]),
        )
        for row in rows
    ]


def fetch_clusters_for_run(database_path: Path, run_id: str) -> list[AnalysisCluster]:
    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                cluster_id, cluster_index, review_ids_json, review_count,
                representative_review_id, keyphrases_json, noise_flag, sentiment_score
            FROM clusters
            WHERE run_id = ?
            ORDER BY cluster_index ASC, cluster_id ASC
            """,
            (run_id,),
        ).fetchall()

    return [
        AnalysisCluster(
            cluster_id=row["cluster_id"],
            cluster_index=row["cluster_index"],
            review_ids=json.loads(row["review_ids_json"]),
            review_count=row["review_count"],
            representative_review_id=row["representative_review_id"],
            keyphrases=json.loads(row["keyphrases_json"]),
            sentiment_score=row["sentiment_score"],
            noise=bool(row["noise_flag"]),
        )
        for row in rows
    ]


def update_run_status(
    database_path: Path,
    run_id: str,
    status: RunStatus,
    *,
    error_message: str | None = None,
) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE runs
            SET status = ?, error_json = ?
            WHERE run_id = ?
            """,
            (
                status.value,
                json.dumps({"message": error_message}) if error_message else None,
                run_id,
            ),
        )
        connection.commit()


def update_run_ingestion_result(
    database_path: Path,
    run_id: str,
    result: IngestionResult,
) -> None:
    with connect(database_path) as connection:
        metrics_row = connection.execute(
            "SELECT metrics_json FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        metrics = {}
        if metrics_row is not None and metrics_row["metrics_json"]:
            metrics = json.loads(metrics_row["metrics_json"])
        metrics["ingestion"] = result.model_dump(mode="json")
        connection.execute(
            """
            UPDATE runs
            SET
                status = ?,
                artifact_dir = ?,
                metrics_json = ?,
                error_json = NULL
            WHERE run_id = ?
            """,
            (
                RunStatus.INGESTED.value,
                str(Path(result.raw_snapshot_path).parent),
                json.dumps(metrics, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()


def update_run_analysis_result(
    database_path: Path,
    run_id: str,
    result: AnalysisResult,
) -> None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
        metrics["analysis"] = result.model_dump(mode="json")
        connection.execute(
            """
            UPDATE runs
            SET
                status = ?,
                artifact_dir = ?,
                metrics_json = ?,
                error_json = NULL
            WHERE run_id = ?
            """,
            (
                RunStatus.ANALYZED.value,
                str(Path(result.artifact_path).parent),
                json.dumps(metrics, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()


def update_run_summarization_result(
    database_path: Path,
    run_id: str,
    result: SummarizationResult,
) -> None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
        metrics["summarization"] = {
            "summary_path": result.summary_path,
            "usage": result.usage.model_dump(mode="json"),
        }
        connection.execute(
            """
            UPDATE runs
            SET
                status = ?,
                summary_path = ?,
                metrics_json = ?,
                error_json = NULL
            WHERE run_id = ?
            """,
            (
                RunStatus.SUMMARIZED.value,
                result.summary_path,
                json.dumps(metrics, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()


def update_run_render_result(
    database_path: Path,
    run_id: str,
    result: RenderResult,
) -> None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
        metrics["rendering"] = result.model_dump(mode="json")
        connection.execute(
            """
            UPDATE runs
            SET
                status = ?,
                artifact_dir = ?,
                metrics_json = ?,
                error_json = NULL
            WHERE run_id = ?
            """,
            (
                RunStatus.RENDERED.value,
                result.artifact_dir,
                json.dumps(metrics, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()


def update_run_docs_publish_result(
    database_path: Path,
    run_id: str,
    result: DocsPublishResult,
) -> None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
        metrics["publish_docs"] = result.model_dump(mode="json")
        connection.execute(
            """
            UPDATE runs
            SET
                status = ?,
                gdoc_id = ?,
                gdoc_heading_id = ?,
                gdoc_deep_link = ?,
                metrics_json = ?,
                error_json = NULL
            WHERE run_id = ?
            """,
            (
                RunStatus.PUBLISHED_DOCS.value,
                result.gdoc_id,
                result.gdoc_heading_id,
                result.gdoc_deep_link,
                json.dumps(metrics, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()


def update_run_gmail_publish_result(
    database_path: Path,
    run_id: str,
    result: GmailPublishResult,
) -> None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
        metrics["publish_gmail"] = result.model_dump(mode="json")
        connection.execute(
            """
            UPDATE runs
            SET
                status = ?,
                gmail_draft_id = ?,
                gmail_message_id = ?,
                metrics_json = ?,
                error_json = NULL
            WHERE run_id = ?
            """,
            (
                RunStatus.COMPLETED.value,
                result.gmail_draft_id,
                result.gmail_message_id,
                json.dumps(metrics, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()


def update_run_orchestration_result(
    database_path: Path,
    run_id: str,
    result: PipelineRunResult,
) -> None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
        metrics["orchestration"] = result.model_dump(mode="json")
        connection.execute(
            """
            UPDATE runs
            SET
                completed_at = CASE WHEN ? = ? THEN ? ELSE completed_at END,
                metrics_json = ?
            WHERE run_id = ?
            """,
            (
                result.final_status,
                RunStatus.COMPLETED.value,
                utc_now(),
                json.dumps(metrics, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()


def upsert_reviews(database_path: Path, reviews: list[RawReview]) -> dict[str, int]:
    inserted = 0
    updated = 0
    unchanged = 0
    with connect(database_path) as connection:
        for review in reviews:
            current = connection.execute(
                """
                SELECT
                    product_key, source, external_id, rating, title, body_raw, body_scrubbed,
                    reviewed_at, locale, raw_json
                FROM reviews
                WHERE review_id = ?
                """,
                (review.review_id,),
            ).fetchone()

            payload = (
                review.review_id,
                review.product_key,
                review.source,
                review.external_id,
                review.rating,
                review.title,
                review.body_raw,
                review.body_scrubbed,
                review.reviewed_at.isoformat(),
                review.locale,
                serialize_payload(review.raw_payload),
                utc_now(),
            )

            if current is None:
                connection.execute(
                    """
                    INSERT INTO reviews (
                        review_id, product_key, source, external_id, rating, title, body_raw,
                        body_scrubbed, reviewed_at, locale, raw_json, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                inserted += 1
                continue

            next_values = {
                "product_key": review.product_key,
                "source": review.source,
                "external_id": review.external_id,
                "rating": review.rating,
                "title": review.title,
                "body_raw": review.body_raw,
                "body_scrubbed": review.body_scrubbed,
                "reviewed_at": review.reviewed_at.isoformat(),
                "locale": review.locale,
                "raw_json": serialize_payload(review.raw_payload),
            }
            current_values = {key: current[key] for key in current.keys()}
            if current_values == next_values:
                unchanged += 1
                continue

            connection.execute(
                """
                UPDATE reviews
                SET
                    product_key = ?,
                    source = ?,
                    external_id = ?,
                    rating = ?,
                    title = ?,
                    body_raw = ?,
                    body_scrubbed = ?,
                    reviewed_at = ?,
                    locale = ?,
                    raw_json = ?,
                    ingested_at = ?
                WHERE review_id = ?
                """,
                (
                    review.product_key,
                    review.source,
                    review.external_id,
                    review.rating,
                    review.title,
                    review.body_raw,
                    review.body_scrubbed,
                    review.reviewed_at.isoformat(),
                    review.locale,
                    serialize_payload(review.raw_payload),
                    utc_now(),
                    review.review_id,
                ),
            )
            updated += 1
        connection.commit()
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged}


def get_cached_embedding(
    *,
    database_path: Path,
    review_id: str,
    embedding_model: str,
    embedding_sha1: str,
) -> list[float] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT vector
            FROM review_embeddings
            WHERE review_id = ? AND embedding_model = ? AND embedding_sha1 = ?
            """,
            (review_id, embedding_model, embedding_sha1),
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                SELECT vector
                FROM review_embeddings
                WHERE embedding_model = ? AND embedding_sha1 = ?
                LIMIT 1
                """,
                (embedding_model, embedding_sha1),
            ).fetchone()
    if row is None:
        return None
    vector = json.loads(row["vector"])
    return [float(value) for value in vector]


def upsert_review_embedding(
    *,
    database_path: Path,
    review_id: str,
    embedding_model: str,
    embedding_sha1: str,
    vector: list[float],
) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO review_embeddings (
                review_id, embedding_model, embedding_sha1, vector, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                embedding_model = excluded.embedding_model,
                embedding_sha1 = excluded.embedding_sha1,
                vector = excluded.vector,
                created_at = excluded.created_at
            """,
            (
                review_id,
                embedding_model,
                embedding_sha1,
                json.dumps(vector),
                utc_now(),
            ),
        )
        connection.commit()


def replace_clusters_for_run(
    database_path: Path,
    run_id: str,
    clusters: list[AnalysisCluster],
) -> None:
    with connect(database_path) as connection:
        connection.execute("DELETE FROM clusters WHERE run_id = ?", (run_id,))
        for cluster in clusters:
            connection.execute(
                """
                INSERT INTO clusters (
                    cluster_id, run_id, cluster_index, review_ids_json, review_count,
                    representative_review_id, keyphrases_json, noise_flag,
                    sentiment_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster.cluster_id,
                    run_id,
                    cluster.cluster_index,
                    json.dumps(cluster.review_ids),
                    cluster.review_count,
                    cluster.representative_review_id,
                    json.dumps(cluster.keyphrases),
                    int(cluster.noise),
                    cluster.sentiment_score,
                    utc_now(),
                ),
            )
        connection.commit()


def upsert_report(
    database_path: Path,
    run_id: str,
    report: PulseReport,
    artifact_path: Path,
) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO reports (
                report_id, run_id, report_json, artifact_path, created_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                report_json = excluded.report_json,
                artifact_path = excluded.artifact_path,
                created_at = excluded.created_at
            """,
            (
                run_id,
                run_id,
                report.model_dump_json(indent=2),
                str(artifact_path),
                utc_now(),
            ),
        )
        connection.commit()


def fetch_report(database_path: Path, run_id: str) -> PulseReport | None:
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT report_json
            FROM reports
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return PulseReport.model_validate_json(row["report_json"])


def fetch_render_result(database_path: Path, run_id: str) -> RenderResult | None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
    payload = metrics.get("rendering")
    if payload is None:
        return None
    return RenderResult.model_validate(payload)


def fetch_ingestion_result(database_path: Path, run_id: str) -> IngestionResult | None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
    payload = metrics.get("ingestion")
    if payload is None:
        return None
    return IngestionResult.model_validate(payload)


def fetch_analysis_result(database_path: Path, run_id: str) -> AnalysisResult | None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
    payload = metrics.get("analysis")
    if payload is None:
        return None
    return AnalysisResult.model_validate(payload)


def fetch_summarization_result(database_path: Path, run_id: str) -> SummarizationResult | None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
    payload = metrics.get("summarization")
    if not isinstance(payload, dict):
        return None
    report = fetch_report(database_path, run_id)
    if report is None:
        return None
    usage_payload = payload.get("usage")
    summary_path = payload.get("summary_path")
    if not isinstance(usage_payload, dict) or not isinstance(summary_path, str):
        return None
    return SummarizationResult(
        run_id=run_id,
        product_key=report.product_key,
        iso_week=report.iso_week,
        summary_path=summary_path,
        usage=LLMUsage.model_validate(usage_payload),
        report=report,
    )


def fetch_docs_publish_result(database_path: Path, run_id: str) -> DocsPublishResult | None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
    payload = metrics.get("publish_docs")
    if payload is None:
        return None
    return DocsPublishResult.model_validate(payload)


def fetch_gmail_publish_result(database_path: Path, run_id: str) -> GmailPublishResult | None:
    with connect(database_path) as connection:
        metrics = _load_metrics(connection, run_id)
    payload = metrics.get("publish_gmail")
    if payload is None:
        return None
    return GmailPublishResult.model_validate(payload)


def fetch_delivery_result(database_path: Path, run_id: str) -> DeliveryResult | None:
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                gdoc_id, gdoc_heading_id, gdoc_deep_link, gmail_draft_id, gmail_message_id
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    values = {
        "gdoc_id": row["gdoc_id"],
        "gdoc_heading_id": row["gdoc_heading_id"],
        "gdoc_deep_link": row["gdoc_deep_link"],
        "gmail_draft_id": row["gmail_draft_id"],
        "gmail_message_id": row["gmail_message_id"],
    }
    if not any(values.values()):
        return None
    return DeliveryResult(
        gdoc_id=row["gdoc_id"],
        gdoc_heading_id=row["gdoc_heading_id"],
        gdoc_deep_link=row["gdoc_deep_link"],
        gmail_draft_id=row["gmail_draft_id"],
        gmail_message_id=row["gmail_message_id"],
        delivery_status="persisted",
    )


def record_delivery_event(
    database_path: Path,
    *,
    run_id: str,
    channel: str,
    idempotency_key: str,
    status: str,
    payload: dict[str, object],
    metadata: dict[str, object],
    external_id: str | None = None,
) -> None:
    payload_text = json.dumps(payload, sort_keys=True, default=str)
    metadata_text = json.dumps(metadata, sort_keys=True, default=str)
    payload_sha1 = sha1(payload_text.encode("utf-8")).hexdigest()
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO delivery_events (
                run_id, channel, idempotency_key, status, external_id, payload_sha1,
                occurred_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                channel,
                idempotency_key,
                status,
                external_id,
                payload_sha1,
                utc_now(),
                metadata_text,
            ),
        )
        connection.commit()


def list_runs(
    database_path: Path,
    *,
    limit: int = 20,
    product_key: str | None = None,
) -> list[RunHistoryEntry]:
    clauses = []
    values: list[object] = []
    if product_key:
        clauses.append("product_key = ?")
        values.append(product_key)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                run_id,
                product_key,
                iso_week,
                status,
                started_at,
                completed_at,
                gdoc_deep_link,
                gmail_draft_id,
                gmail_message_id,
                error_json
            FROM runs
            {where_sql}
            ORDER BY started_at DESC, run_id DESC
            LIMIT ?
            """,
            (*values, limit),
        ).fetchall()
    history: list[RunHistoryEntry] = []
    for row in rows:
        error_message = None
        if row["error_json"]:
            try:
                payload = json.loads(row["error_json"])
            except json.JSONDecodeError:
                payload = {"message": row["error_json"]}
            error_value = payload.get("message")
            if isinstance(error_value, str):
                error_message = error_value
        history.append(
            RunHistoryEntry(
                run_id=row["run_id"],
                product_key=row["product_key"],
                iso_week=row["iso_week"],
                status=row["status"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                gdoc_deep_link=row["gdoc_deep_link"],
                gmail_draft_id=row["gmail_draft_id"],
                gmail_message_id=row["gmail_message_id"],
                error_message=error_message,
            )
        )
    return history


def summarize_database_counts(database_path: Path) -> dict[str, int]:
    with connect(database_path) as connection:
        return {
            "products": connection.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "runs": connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
            "reviews": connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
            "clusters": connection.execute("SELECT COUNT(*) FROM clusters").fetchone()[0],
            "reports": connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
            "delivery_events": connection.execute(
                "SELECT COUNT(*) FROM delivery_events"
            ).fetchone()[0],
        }


def count_runs_by_status(database_path: Path) -> dict[str, int]:
    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM runs
            GROUP BY status
            ORDER BY status ASC
            """
        ).fetchall()
    return {str(row["status"]): int(row["count"]) for row in rows}


def list_delivery_events(
    database_path: Path,
    *,
    limit: int = 20,
) -> list[DeliveryEventEntry]:
    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                event_id,
                run_id,
                channel,
                status,
                external_id,
                occurred_at
            FROM delivery_events
            ORDER BY occurred_at DESC, event_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        DeliveryEventEntry(
            event_id=row["event_id"],
            run_id=row["run_id"],
            channel=row["channel"],
            status=row["status"],
            external_id=row["external_id"],
            occurred_at=row["occurred_at"],
        )
        for row in rows
    ]


def _load_metrics(connection: sqlite3.Connection, run_id: str) -> dict[str, object]:
    metrics_row = connection.execute(
        "SELECT metrics_json FROM runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    metrics: dict[str, object] = {}
    if metrics_row is not None and metrics_row["metrics_json"]:
        metrics = json.loads(metrics_row["metrics_json"])
    return metrics


def _load_ingested_review_ids(connection: sqlite3.Connection, run_id: str) -> list[str]:
    metrics = _load_metrics(connection, run_id)
    ingestion = metrics.get("ingestion")
    if not isinstance(ingestion, dict):
        return []
    review_ids = ingestion.get("review_ids")
    if not isinstance(review_ids, list):
        return []
    return [review_id for review_id in review_ids if isinstance(review_id, str)]


def _migrate_schema(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, "clusters", "keyphrases_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(connection, "clusters", "noise_flag", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "clusters", "sentiment_score", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "runs", "gdoc_deep_link", "TEXT")


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )
