import sqlite3
from pathlib import Path

from agent.config import load_product_catalog
from agent.storage import create_or_get_run, initialize_database, sync_products
from agent.windowing import build_review_window


def test_initialize_database_creates_core_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "pulse.db"

    initialize_database(database_path)

    connection = sqlite3.connect(database_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    tables = {row[0] for row in rows}

    assert {
        "products",
        "runs",
        "reviews",
        "review_embeddings",
        "clusters",
        "reports",
        "delivery_events",
    }.issubset(tables)


def test_create_or_get_run_persists_deterministic_run(tmp_path: Path) -> None:
    database_path = tmp_path / "pulse.db"
    initialize_database(database_path)
    catalog = load_product_catalog(Path.cwd() / "products.yaml")
    sync_products(database_path, catalog)
    window = build_review_window("2026-W17", 10, "Asia/Calcutta")

    first = create_or_get_run(database_path, "indmoney", window)
    second = create_or_get_run(database_path, "indmoney", window)

    assert first.run_id == second.run_id
    assert first.report_anchor == "pulse-indmoney-2026-W17"
