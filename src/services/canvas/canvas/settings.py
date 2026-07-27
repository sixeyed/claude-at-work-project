"""Canvas service configuration (Conventions §8, design doc 03 §6)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "local"
    log_level: str = "info"

    postgres_dsn: str

    # R1 caches the active document's state vector; R2 is the relay backplane.
    # Canvas produces no jobs, so it has no R3 connection.
    redis_cache_url: str
    redis_realtime_url: str

    auth_issuer: str
    auth_audience: str = "collabhub"
    auth_jwks_url: str

    canvas_snapshot_interval_seconds: int = 10
    canvas_snapshot_every_updates: int = 200
    canvas_max_doc_bytes: int = 26_214_400
    canvas_awareness_timeout_seconds: int = 30

    otel_exporter_otlp_endpoint: str | None = None
