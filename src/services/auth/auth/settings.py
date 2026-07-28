"""Auth service configuration.

All config comes from environment variables (Conventions §8). Field names map to
`SCREAMING_SNAKE_CASE` vars; every var here also appears in `.env.example`.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
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


class OidcProvider(BaseModel):
    """An upstream OpenID Connect provider this service federates to (§5.1).

    Two authorities, and the split is the whole reason this model exists.

    `authority` is the provider's *identity*: the value it puts in `iss`, and
    the URL the user's browser is sent to. `internal_authority` is merely an
    *address* — where this process can reach the same provider for discovery,
    the token exchange and JWKS.

    They are the same in most deployments and different in two that matter:
    locally, where the browser cannot resolve `dex` and this container cannot
    resolve its own `localhost`; and in any cluster whose public hostname is not
    its in-cluster service name. Conflating them produces a service that works
    from a browser and cannot complete a token exchange, or vice versa.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    authority: str
    internal_authority: str = ""
    client_id: str
    client_secret: str
    scopes: list[str] = ["openid", "profile", "email"]

    @property
    def back_channel(self) -> str:
        """Where to reach the provider from here. Falls back to the public URL."""
        return (self.internal_authority or self.authority).rstrip("/")

    @property
    def front_channel(self) -> str:
        """The provider's public identity — `iss`, and where the browser goes."""
        return self.authority.rstrip("/")


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

    # Upstream identity providers. JSON in the environment, e.g.
    # OIDC_PROVIDERS='[{"name":"dex","authority":"http://localhost:5556/dex",...}]'
    oidc_providers: list[OidcProvider] = []

    # Both halves of a login are single-use keys in R1 with a ceiling on how
    # long they may sit unspent: the outbound state while the user is at the
    # IdP, and the authorization code between the callback and the SPA
    # exchanging it.
    auth_login_state_ttl_seconds: int = 300
    auth_code_ttl_seconds: int = 60

    # Every user joins this shared workspace on first sign-in, so two local
    # accounts have somewhere to meet. Local only.
    auth_demo_workspace_name: str = "CollabHub Demo"

    # Where the SPA is sent once identity is established. The only redirect
    # target this service will ever use — it is never taken from a request, so
    # there is no open redirect to validate against a list.
    spa_redirect_uri: str = ""

    # Browser origins allowed to call this service. Empty — the default — installs
    # no CORS middleware at all, which is right when the SPA and the API share an
    # origin behind one ingress. Locally they do not.
    #
    # These origins are trusted with *credentials*: the refresh cookie is sent on
    # requests from them (register D22). A wildcard is refused outright by the
    # browser in that mode, which is the right instinct — keep the list short.
    cors_allowed_origins: list[str] = []

    # `Secure` on the refresh cookie. True everywhere, including locally, because
    # browsers treat `http://localhost` as a trustworthy origin and accept it.
    # The only reason to turn it off is a browser that disagrees; doing so in a
    # deployed environment would put the session token on the wire in clear.
    auth_cookie_secure: bool = True

    otel_exporter_otlp_endpoint: str | None = None

    @property
    def is_local(self) -> bool:
        return self.app_env == LOCAL_ENV

    def service_client(self, client_id: str) -> ServiceClient | None:
        return next((c for c in self.auth_service_clients if c.client_id == client_id), None)

    def oidc_provider(self, name: str) -> OidcProvider | None:
        return next((p for p in self.oidc_providers if p.name == name), None)
