"""Worker configuration (Conventions §8, design doc 05 §6).

No `POSTGRES_DSN`. Design doc 05 §2 mentions read access to service databases,
but that contradicts the rule that a service never reads another service's
tables (CLAUDE.md; Conventions §2). The scaffold takes no position: the Worker
gets no database connection until that is settled, and the write-back path it
does have is Asset's internal endpoint (D14, already decided).
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
    # be split later without a code change (register D17, still open).
    worker_streams: str = "jobs:index,jobs:thumbnail,jobs:notify,jobs:export,jobs:retention"
    worker_max_attempts: int = 5
    worker_visibility_timeout_seconds: int = 60
    worker_batch_size: int = 16

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
