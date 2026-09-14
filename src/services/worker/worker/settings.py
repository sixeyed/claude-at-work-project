"""Worker configuration (Conventions §8, design doc 05 §6).

No `POSTGRES_DSN`, and there never will be. Register D25 settled that the Worker
touches no service database in either direction: handlers get what they need
from the job payload, or from the owning service's internal endpoint with a
service token. See docs/adr/260727-worker-never-reads-service-databases.md.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "local"
    log_level: str = "info"

    # R3 only. The Worker neither caches nor serves real-time traffic.
    redis_streams_url: str

    elasticsearch_url: str

    object_store_endpoint: str
    object_store_access_key: str = ""
    object_store_secret_key: str = ""
    object_store_bucket: str = "collabhub-assets"

    # Which streams this deployment consumes, so CPU-heavy and IO-heavy pools can
    # be split later without a code change (register D17, still open). Only
    # streams with handlers belong here: the Worker refuses to start on one it
    # cannot handle, rather than dead-lettering every job on it. `jobs:index` is
    # the only one built.
    worker_streams: str = "jobs:index"
    worker_max_attempts: int = 5
    worker_visibility_timeout_seconds: int = 60
    worker_batch_size: int = 16
    # Dead-letter entries hold job payloads, which for index jobs means message
    # bodies (doc 05 §8) — so the dead stream is capped deliberately, not left
    # to grow.
    worker_dead_letter_maxlen: int = 10_000

    # Auth is a runtime dependency: the Worker exchanges these for a service
    # token to call Asset's internal endpoint (Conventions §5.5).
    service_token_url: str = ""
    worker_service_client_id: str = "worker"
    worker_service_client_secret: str = ""
    asset_internal_url: str = ""

    otel_exporter_otlp_endpoint: str | None = None

    @property
    def streams(self) -> list[str]:
        return [s.strip() for s in self.worker_streams.split(",") if s.strip()]
