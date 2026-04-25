from pathlib import Path

from fastapi.testclient import TestClient

from agent.mcp.server import app


def test_api_overview_returns_core_sections(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))
    monkeypatch.setenv("PULSE_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("PULSE_SCHEDULER_DAY_OF_WEEK", "0")
    monkeypatch.setenv("PULSE_SCHEDULER_HOUR_24", "9")
    monkeypatch.setenv("PULSE_SCHEDULER_MINUTE", "15")

    client = TestClient(app)
    response = client.get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"]["status"] == "ok"
    assert "scheduler" in payload
    assert "services" in payload
    assert "issues" in payload
    assert "fleet" in payload
    assert "counts" in payload
    assert "products" in payload
    assert "jobs" in payload
    assert payload["scheduler"]["status"] == "active"
    assert payload["scheduler"]["target_product_key"] == "indmoney"
    assert payload["products"] == [
        {
            "product_key": "indmoney",
            "display_name": "INDMoney",
            "active": True,
            "stakeholders": {
                "to": ["gptshivam595@gmail.com"],
                "cc": ["gptshivam595@gmail.com"],
                "bcc": [],
            },
        }
    ]


def test_api_dashboard_alias_returns_richer_payload(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))

    client = TestClient(app)
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert "recent_delivery_events" in payload
    assert "services" in payload
    assert "fleet" in payload


def test_api_completion_reports_partial_without_google_token(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))
    monkeypatch.delenv("GOOGLE_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_MCP_TOKEN_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", str(tmp_path / "missing-token.json"))

    client = TestClient(app)
    response = client.get("/api/completion")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "partial"
    assert payload["google_auth"]["token_available"] is False


def test_api_scheduler_can_toggle_enabled_state(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "pulse.db"
    monkeypatch.setenv("PULSE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PULSE_PRODUCTS_PATH", str(Path.cwd() / "products.yaml"))
    monkeypatch.setenv("PULSE_SCHEDULER_ENABLED", "false")

    client = TestClient(app)

    enable_response = client.post("/api/scheduler", json={"enabled": True})
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True
    assert enable_response.json()["target_product_key"] == "indmoney"

    scheduler_response = client.get("/api/scheduler")
    assert scheduler_response.status_code == 200
    assert scheduler_response.json()["enabled"] is True
