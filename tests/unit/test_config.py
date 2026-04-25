from pathlib import Path

import pytest

from agent.config import load_product_catalog


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

