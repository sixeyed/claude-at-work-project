"""`python -m auth.migrate` — bring Auth's database up to head.

A separate entry point rather than something the service does while starting up:
migrations are a deployment step, and five replicas rolling out at once must not
all try to run them. Locally the container entrypoint invokes this before the
server; in Kubernetes it belongs in a pre-upgrade Job.
"""

from __future__ import annotations

import asyncio
import logging

from auth.migrations import upgrade_to_head
from auth.settings import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    asyncio.run(upgrade_to_head(settings.postgres_dsn))


if __name__ == "__main__":
    main()
