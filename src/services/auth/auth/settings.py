"""Auth service configuration.

All config comes from environment variables (Conventions §8). Field names map to
`SCREAMING_SNAKE_CASE` vars; every var here also appears in `.env.example`.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "local"
    log_level: str = "info"

    # Auth owns its database and uses R1 for the token denylist and the userinfo
    # cache. It does not touch R2 or R3.
    postgres_dsn: str
    redis_cache_url: str

    auth_issuer: str
    auth_audience: str = "collabhub"
    auth_internal_audience: str = "collabhub-internal"

    # RS256 signing material. Empty here; supplied as a secret at deploy time.
    auth_signing_key: str = ""
    auth_previous_keys: str = ""
    auth_access_token_minutes: int = 15
    auth_refresh_token_days: int = 30

    spa_redirect_uri: str = ""

    otel_exporter_otlp_endpoint: str | None = None
