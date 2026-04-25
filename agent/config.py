from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StakeholderList(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)


class ProductConfig(BaseModel):
    product_key: str
    display_name: str
    appstore_app_id: str
    playstore_package: str
    country_code: str = Field(min_length=2, max_length=2)
    active: bool = True
    stakeholders: StakeholderList = Field(default_factory=StakeholderList)

    @field_validator("product_key")
    @classmethod
    def normalize_product_key(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "-").replace("_", "-")
        if not normalized:
            msg = "product_key must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return value.upper()


class ProductCatalog(BaseModel):
    products: list[ProductConfig]

    @model_validator(mode="after")
    def ensure_unique_product_keys(self) -> ProductCatalog:
        keys = [product.product_key for product in self.products]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            msg = f"Duplicate product_key values found: {sorted(duplicates)}"
            raise ValueError(msg)
        return self

    def get_product(self, product_key: str) -> ProductConfig:
        normalized = product_key.strip().lower().replace(" ", "-").replace("_", "-")
        for product in self.products:
            if product.product_key == normalized:
                return product
        msg = f"Unknown product_key: {product_key}"
        raise KeyError(msg)


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PULSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    products_path: Path = Path("products.yaml")
    database_path: Path = Path("data/pulse.db")
    default_review_window_weeks: int = 10
    timezone: str = "Asia/Calcutta"
    log_level: str = "INFO"
    docs_mcp_transport: str = "http"
    docs_mcp_base_url: str = "http://127.0.0.1:8000"
    docs_mcp_timeout_seconds: int = 30
    gmail_mcp_transport: str = "http"
    gmail_mcp_base_url: str = "http://127.0.0.1:8000"
    gmail_mcp_timeout_seconds: int = 30
    api_cors_origins: str = ""
    confirm_send: bool = False
    scheduler_enabled: bool = False
    scheduler_day_of_week: int = 0
    scheduler_hour_24: int = 9
    scheduler_minute: int = 0
    orchestration_retry_attempts: int = 2
    orchestration_retry_backoff_seconds: float = 0.0
    embedding_provider: str = "local"
    embedding_model: str = "hash-v1"
    embedding_dimensions: int = 64
    analysis_min_review_length: int = 20
    analysis_min_cluster_size: int = 2
    analysis_similarity_threshold: float = 0.72
    llm_provider: str = "heuristic"
    llm_model: str = "heuristic-v1"
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 1
    llm_cost_cap_usd: float = 1.0

    @field_validator("default_review_window_weeks")
    @classmethod
    def validate_window_weeks(cls, value: int) -> int:
        if not 8 <= value <= 12:
            msg = "default_review_window_weeks must be between 8 and 12"
            raise ValueError(msg)
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            msg = f"Unknown timezone: {value}"
            raise ValueError(msg) from exc
        return value

    @field_validator("embedding_provider")
    @classmethod
    def validate_embedding_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"local", "openai"}:
            msg = "embedding_provider must be 'local' or 'openai'"
            raise ValueError(msg)
        return normalized

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(cls, value: int) -> int:
        if value <= 0:
            msg = "embedding_dimensions must be positive"
            raise ValueError(msg)
        return value

    @field_validator("analysis_min_review_length")
    @classmethod
    def validate_analysis_min_review_length(cls, value: int) -> int:
        if value <= 0:
            msg = "analysis_min_review_length must be positive"
            raise ValueError(msg)
        return value

    @field_validator("analysis_min_cluster_size")
    @classmethod
    def validate_analysis_min_cluster_size(cls, value: int) -> int:
        if value < 2:
            msg = "analysis_min_cluster_size must be at least 2"
            raise ValueError(msg)
        return value

    @field_validator("analysis_similarity_threshold")
    @classmethod
    def validate_analysis_similarity_threshold(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            msg = "analysis_similarity_threshold must be between 0 and 1"
            raise ValueError(msg)
        return value

    @field_validator("docs_mcp_transport")
    @classmethod
    def validate_docs_mcp_transport(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"stdio", "http", "stub"}:
            msg = "docs_mcp_transport must be 'stdio', 'http', or 'stub'"
            raise ValueError(msg)
        return normalized

    @field_validator("docs_mcp_timeout_seconds")
    @classmethod
    def validate_docs_mcp_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            msg = "docs_mcp_timeout_seconds must be positive"
            raise ValueError(msg)
        return value

    @field_validator("gmail_mcp_transport")
    @classmethod
    def validate_gmail_mcp_transport(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"stdio", "http", "stub"}:
            msg = "gmail_mcp_transport must be 'stdio', 'http', or 'stub'"
            raise ValueError(msg)
        return normalized

    @field_validator("gmail_mcp_timeout_seconds")
    @classmethod
    def validate_gmail_mcp_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            msg = "gmail_mcp_timeout_seconds must be positive"
            raise ValueError(msg)
        return value

    @field_validator("orchestration_retry_attempts")
    @classmethod
    def validate_orchestration_retry_attempts(cls, value: int) -> int:
        if value < 1:
            msg = "orchestration_retry_attempts must be at least 1"
            raise ValueError(msg)
        return value

    @field_validator("scheduler_day_of_week")
    @classmethod
    def validate_scheduler_day_of_week(cls, value: int) -> int:
        if value < 0 or value > 6:
            msg = "scheduler_day_of_week must be between 0 (Monday) and 6 (Sunday)"
            raise ValueError(msg)
        return value

    @field_validator("scheduler_hour_24")
    @classmethod
    def validate_scheduler_hour_24(cls, value: int) -> int:
        if value < 0 or value > 23:
            msg = "scheduler_hour_24 must be between 0 and 23"
            raise ValueError(msg)
        return value

    @field_validator("scheduler_minute")
    @classmethod
    def validate_scheduler_minute(cls, value: int) -> int:
        if value < 0 or value > 59:
            msg = "scheduler_minute must be between 0 and 59"
            raise ValueError(msg)
        return value

    @field_validator("orchestration_retry_backoff_seconds")
    @classmethod
    def validate_orchestration_retry_backoff_seconds(cls, value: float) -> float:
        if value < 0:
            msg = "orchestration_retry_backoff_seconds must be zero or greater"
            raise ValueError(msg)
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"heuristic"}:
            msg = "llm_provider must currently be 'heuristic'"
            raise ValueError(msg)
        return normalized

    @field_validator("llm_timeout_seconds")
    @classmethod
    def validate_llm_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            msg = "llm_timeout_seconds must be positive"
            raise ValueError(msg)
        return value

    @field_validator("llm_max_retries")
    @classmethod
    def validate_llm_max_retries(cls, value: int) -> int:
        if value < 0:
            msg = "llm_max_retries must be zero or greater"
            raise ValueError(msg)
        return value

    @field_validator("llm_cost_cap_usd")
    @classmethod
    def validate_llm_cost_cap_usd(cls, value: float) -> float:
        if value < 0:
            msg = "llm_cost_cap_usd must be zero or greater"
            raise ValueError(msg)
        return value

    def resolve_products_path(self) -> Path:
        if self.products_path.is_absolute():
            return self.products_path
        return Path.cwd() / self.products_path

    def resolve_database_path(self) -> Path:
        if self.database_path.is_absolute():
            return self.database_path
        return Path.cwd() / self.database_path

    def resolve_api_cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.api_cors_origins.split(",")
            if origin.strip()
        ]


def load_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings()


def load_product_catalog(products_path: Path) -> ProductCatalog:
    if not products_path.exists():
        msg = f"Products file not found: {products_path}"
        raise FileNotFoundError(msg)

    with products_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    return ProductCatalog.model_validate(payload)
