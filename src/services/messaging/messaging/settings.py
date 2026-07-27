"""Messaging service configuration (Conventions §8, design doc 02 §6)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "local"
    log_level: str = "info"

    postgres_dsn: str

    # Messaging is the one service that uses all three Redis instances, and they
    # are not interchangeable: R1 caches membership, R2 is the Socket.IO
    # backplane, R3 carries index jobs.
    redis_cache_url: str
    redis_realtime_url: str
    redis_streams_url: str

    auth_issuer: str
    auth_audience: str = "collabhub"
    auth_jwks_url: str

    messaging_max_body_chars: int = 8000
    messaging_max_attachments: int = 10

    otel_exporter_otlp_endpoint: str | None = None
