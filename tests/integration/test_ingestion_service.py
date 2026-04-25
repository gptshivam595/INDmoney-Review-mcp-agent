from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agent.config import load_product_catalog, load_runtime_settings
from agent.ingestion.appstore import parse_appstore_payload
from agent.ingestion.playstore import normalize_playstore_reviews
from agent.ingestion.service import ingest_reviews_for_run
from agent.storage import create_or_get_run, initialize_database, sync_products
from agent.windowing import build_review_window


def test_ingestion_service_replays_fixtures_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))
    initialize_database(database_path)

    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    sync_products(database_path, catalog)
    product = catalog.get_product("indmoney")
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")
    run = create_or_get_run(database_path, product.product_key, window)
    settings = load_runtime_settings()

    appstore_payload = json.loads(
        (Path.cwd() / "tests/fixtures/appstore_reviews_page1.json").read_text(encoding="utf-8")
    )
    playstore_payload = json.loads(
        (Path.cwd() / "tests/fixtures/playstore_reviews_page1.json").read_text(encoding="utf-8")
    )
    since_date = window.window_start

    first = ingest_reviews_for_run(
        settings=settings,
        database_path=database_path,
        product=product,
        run=run,
        appstore_fetcher=lambda _product, _since_date: parse_appstore_payload(
            product, appstore_payload, since_date
        ),
        playstore_fetcher=lambda _product, _since_date: normalize_playstore_reviews(
            product, playstore_payload, since_date
        ),
    )
    second = ingest_reviews_for_run(
        settings=settings,
        database_path=database_path,
        product=product,
        run=run,
        appstore_fetcher=lambda _product, _since_date: parse_appstore_payload(
            product, appstore_payload, since_date
        ),
        playstore_fetcher=lambda _product, _since_date: normalize_playstore_reviews(
            product, playstore_payload, since_date
        ),
    )

    connection = sqlite3.connect(database_path)
    review_count = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]

    assert first.inserted == 2
    assert first.updated == 0
    assert second.inserted == 0
    assert second.unchanged == 2
    assert review_count == 2
    assert Path(first.raw_snapshot_path).exists()
