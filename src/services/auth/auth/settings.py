"""Auth service configuration.

All config comes from environment variables (Conventions §8). Field names map to
`SCREAMING_SNAKE_CASE` vars; every var here also appears in `.env.example`.
"""

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_ENV = "local"


class ServiceClient(BaseModel):
    """A service allowed to exchange credentials for an internal token (§5.5).

    A fixed handful of clients, so they live in config rather than a table:
    granting one is a deployment change and revoking one is a secret rotation,
    which is exactly how §5.5 says service tokens are managed.
    """

    client_id: str
    secret: str
    scopes: list[str] = []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = LOCAL_ENV
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
    auth_service_token_minutes: int = 10

    # JSON in the environment, e.g.
    # AUTH_SERVICE_CLIENTS='[{"client_id":"worker","secret":"s","scopes":["assets:write-variants"]}]'
    auth_service_clients: list[ServiceClient] = []

    # Every user joins this shared workspace on first sign-in, so two local
    # accounts have somewhere to meet (see `dev_login_enabled`).
    auth_demo_workspace_name: str = "CollabHub Demo"

    spa_redirect_uri: str = ""

    otel_exporter_otlp_endpoint: str | None = None

    @property
    def is_local(self) -> bool:
        return self.app_env == LOCAL_ENV

    @property
    def dev_login_enabled(self) -> bool:
        """`POST /auth/dev-login` exists only on a laptop.

        It mints a session for any email address with no proof of identity at
        all, which is what makes it useful locally and unthinkable anywhere
        else. Real federation is register D5, still open.
        """
        return self.is_local

    def service_client(self, client_id: str) -> ServiceClient | None:
        return next((c for c in self.auth_service_clients if c.client_id == client_id), None)
