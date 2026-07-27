"""Asset service configuration (Conventions §8, design doc 04 §6)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "local"
    log_level: str = "info"

    postgres_dsn: str

    # Asset produces thumbnail jobs onto R3. It has no cache or real-time need.
    redis_streams_url: str

    auth_issuer: str
    auth_audience: str = "collabhub"
    auth_internal_audience: str = "collabhub-internal"
    auth_jwks_url: str

    # S3-compatible, and only the S3 subset Garage implements — these values
    # point at Azure Blob just as happily.
    object_store_endpoint: str
    object_store_access_key: str = ""
    object_store_secret_key: str = ""
    object_store_bucket: str = "collabhub-assets"
    object_store_presign_ttl_seconds: int = 900

    asset_max_upload_bytes: int = 52_428_800
    asset_allowed_content_types: str = ""

    otel_exporter_otlp_endpoint: str | None = None
