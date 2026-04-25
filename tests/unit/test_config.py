from pathlib import Path

import pytest

from agent.config import RuntimeSettings, load_product_catalog


def test_load_product_catalog_reads_products(tmp_path: Path) -> None:
    products_file = tmp_path / "products.yaml"
    products_file.write_text(
        """
products:
  - product_key: sample
    display_name: Sample
    appstore_app_id: "1"
    playstore_package: "sample.pkg"
    country_code: IN
    stakeholders:
      to: ["a@example.com"]
      cc: []
      bcc: []
""".strip(),
        encoding="utf-8",
    )

    catalog = load_product_catalog(products_file)

    assert catalog.get_product("sample").display_name == "Sample"


def test_load_product_catalog_rejects_duplicate_keys(tmp_path: Path) -> None:
    products_file = tmp_path / "products.yaml"
    products_file.write_text(
        """
products:
  - product_key: dup
    display_name: One
    appstore_app_id: "1"
    playstore_package: "one.pkg"
    country_code: IN
    stakeholders:
      to: []
      cc: []
      bcc: []
  - product_key: dup
    display_name: Two
    appstore_app_id: "2"
    playstore_package: "two.pkg"
    country_code: IN
    stakeholders:
      to: []
      cc: []
      bcc: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_product_catalog(products_file)


def test_runtime_settings_auto_selects_openai_when_api_key_present(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PULSE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("PULSE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PULSE_SUMMARIZATION_PROVIDER", raising=False)
    monkeypatch.delenv("PULSE_SUMMARIZATION_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = RuntimeSettings()

    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-4.1-mini"


def test_runtime_settings_respects_explicit_llm_provider(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PULSE_LLM_PROVIDER", "heuristic")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = RuntimeSettings()

    assert settings.llm_provider == "heuristic"


def test_runtime_settings_reads_legacy_summarization_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PULSE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("PULSE_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PULSE_SUMMARIZATION_PROVIDER", "heuristic")
    monkeypatch.setenv("PULSE_SUMMARIZATION_MODEL", "legacy-model")

    settings = RuntimeSettings()

    assert settings.llm_provider == "heuristic"
    assert settings.llm_model == "legacy-model"
