"""A real Dex for integration tests — the upstream IdP Auth federates to (D5).

Started by testcontainers (`DockerContainer`: there is no Dex module), and
configured with three static accounts so tests can sign in as more than one
person. Moved from Auth's conftest so a test module can import the accounts by
name.

Dex is bound to a *fixed* host port rather than a random one, because an OIDC
issuer is baked into its configuration: the URL in `issuer` is what Dex puts in
`iss` and what the relying party checks against, so it cannot be discovered
after the container starts. The port is deliberately not 5556, so a running
`docker compose up` and a test run do not fight over it.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
from testcontainers.core.container import DockerContainer

from testkit.images import DEX

DEX_IMAGE = DEX
DEX_PORT = 15556

DEX_CLIENT_ID = "collabhub-auth"
DEX_CLIENT_SECRET = "test-client-secret"

# bcrypt of DEX_PASSWORD. Generated once and pinned rather than hashed at test
# setup, because bcrypt at cost 10 is deliberately slow and this is not what is
# being tested.
DEX_PASSWORD = "collabhub"
# nosemgrep: generic.secrets.security.detected-bcrypt-hash.detected-bcrypt-hash — the hash of DEX_PASSWORD above, a test-only credential
DEX_PASSWORD_HASH = "$2b$10$AjNda/ZYuDZgz2nQA9lAPOb3Y.uGW4xYCWXG8wTfnyb9KjviceU/S"

ADA = "ada@collabhub.dev"
GRACE = "grace@collabhub.dev"
ALAN = "alan@collabhub.dev"

# Dex sends `name` as the username, so this is the display name a first sign-in
# provisions the account with — and what its own workspace gets named after.
ADA_NAME = "ada"

DEX_CONFIG = """
issuer: http://localhost:{port}/dex
storage:
  type: memory
web:
  http: 0.0.0.0:5556
oauth2:
  responseTypes: ["code"]
  skipApprovalScreen: true
staticClients:
  - id: {client_id}
    name: CollabHub
    secret: {client_secret}
    redirectURIs:
      - {issuer}/api/v1/auth/callback/dex
enablePasswordDB: true
staticPasswords:
  - email: {ada}
    username: ada
    userID: 6f9619ff-8b86-d011-b42d-00c04fc964ff
    hashFromEnv: DEX_PASSWORD_HASH
  - email: {grace}
    username: grace
    userID: 7a9619ff-8b86-d011-b42d-00c04fc964ff
    hashFromEnv: DEX_PASSWORD_HASH
  - email: {alan}
    username: alan
    userID: 8b9619ff-8b86-d011-b42d-00c04fc964ff
    hashFromEnv: DEX_PASSWORD_HASH
"""


@contextmanager
def start_dex(config_dir: Path, *, relying_party_issuer: str) -> Iterator[str]:
    """Run Dex for the relying party at `relying_party_issuer`; yield Dex's issuer URL.

    The config is generated rather than reusing `docker/dex/config.yaml` so the
    tests do not depend on the compose stack's port being free, and so a change
    to local developer convenience cannot silently change what is tested.
    """
    config = config_dir / "config.yaml"
    config.write_text(
        DEX_CONFIG.format(
            port=DEX_PORT,
            issuer=relying_party_issuer,
            client_id=DEX_CLIENT_ID,
            client_secret=DEX_CLIENT_SECRET,
            ada=ADA,
            grace=GRACE,
            alan=ALAN,
        )
    )
    # Dex reads the config as the non-root user it runs as.
    config.chmod(0o644)

    container = (
        DockerContainer(DEX_IMAGE)
        .with_command("dex serve /etc/dex/config.yaml")
        .with_volume_mapping(str(config), "/etc/dex/config.yaml", "ro")
        .with_env("DEX_PASSWORD_HASH", DEX_PASSWORD_HASH)
        .with_bind_ports(5556, DEX_PORT)
    )

    with container:
        issuer = f"http://localhost:{DEX_PORT}/dex"
        _await_discovery(issuer, container)
        yield issuer


def _await_discovery(issuer: str, container: DockerContainer) -> None:
    """Block until Dex serves its discovery document.

    Polling the endpoint the tests actually use, rather than waiting on a log
    line, means readiness means "answers OIDC" and not "printed something".
    """
    deadline = 30
    for _ in range(deadline * 4):
        try:
            response = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=1.0)
            if response.status_code == httpx.codes.OK:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)

    raise RuntimeError(f"Dex did not become ready within {deadline}s:\n{container.get_logs()}")
