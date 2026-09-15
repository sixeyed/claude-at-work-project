# Test Pyramid A — Layout and testkit — TDD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Three project rules override those skills.** **Stop at red**: after Task 5 nothing else runs
> until Elton has reviewed the failing tests. **Never commit or stage.** Leave the worktree dirty,
> and move files with plain `mv`, never `git mv`, which stages (CLAUDE.md, "Working in this repo").
> Where a skill says "commit", this plan says "leave uncommitted". The new tests here are unit
> tests. The existing integration suite is *run* to prove the move, never extended.

**Goal:** Every service test lives in `tests/unit/` or `tests/integration/`, and a pytest plugin
enforces that. The plugin marks each test by its directory and refuses anything outside the two.
It also cuts unit tests off from the network and Docker. Shared helpers are imported from
`testkit`. No new tests for existing behaviour — those are the backfill.

**Architecture:** A new dev-only workspace member, `src/services/testkit`, registers
`testkit.plugin` through the `pytest11` entry point. Its collection hook marks items by path, and
its setup and teardown hooks switch pytest-socket's guard and a dead `DOCKER_HOST` on and off
around each unit test. Moving the existing tests is a pure restructure, proven by identical
collection counts and a full integration run. The records that make this decision D32 land in
this plan.

**Tech Stack:** Python 3.12, pytest 9.1.1 (`pytester`), pytest-socket 0.8.1, pytest-cov 7.1.0,
testcontainers 4.15.0, uv workspace, hatchling, ruff 0.16 (TID251), bash 3.2.

**Spec:** [01-test-pyramid-design.md](01-test-pyramid-design.md), approved 2026-09-15. This plan
covers its row **A**, Framework 1, and the `plugin` / `dex` / `dexflow` / `auth` modules of
Framework 2.

**Worktree:** `/Users/elton/scm/manning/caw-test-pyramid`, branch `feature/test-pyramid`, from
`main` at `fe345be`.

**Baseline**, measured 2026-09-15 in this worktree:

| Selection | Collected |
|---|---|
| unit (`not integration and not bdd`) | 112 |
| integration | 287 |
| bdd | 43 |
| total | 442 |

The unit layer also passes with sockets blocked:
`uv run --with pytest-socket==0.8.1 pytest -m "not integration and not bdd" -p socket --disable-socket --allow-unix-socket`
gives `112 passed in 6.47s`.

---

## How this plan runs

| Phase | Tasks | Ends with |
|---|---|---|
| 0 — rules | 0 | CLAUDE.md's working rule says what D32 decided |
| 1 — restructure, staying green | 1–3 | `testkit` exists, Auth's helpers are in it, every test is in `unit/` or `integration/`; counts unchanged, integration suite green |
| **RED** | 4–5 | 10 new plugin tests: 6 failing for their stated reason, 4 guards passing — **STOP for review** |
| GREEN | 6–8 | plugin, marker-by-directory in `test.sh`, coverage |
| REFACTOR | 9 | tidy, still green |
| Finish | 10–11 | CLAUDE.md, Conventions §11, register D32, ADR, full verification |

## Decisions already settled

Settled with Elton on 2026-09-15: all twelve in the design. The ones that shape this plan:
- **#1:** testcontainers starts every dependency.
- **#2:** pure policy functions, no fake repositories. Recorded here, but its first worked
  example is deferred to the backfill (see call 7).
- **#3:** the directory decides the layer.
- **#4:** no network or Docker in unit tests.
- **#5:** a `testkit` pytest11 plugin.
- **#11:** coverage is reported, not gated.

## This plan's own calls — yes or no

1. **Dex and Auth's test helpers move into `testkit` now, not in plan B.** Moving five Auth test
   files breaks their `from tests.conftest import …` and `from tests import dexflow`. Those imports
   only work because `tests` is a namespace package spanning every service. It resolves today to
   `['tests', 'src/services/asset/tests', 'src/services/auth/tests', …]`, and Auth sorts first.
   After the move, `tests.integration.conftest` would be just as ambiguous. The new homes:
   - `testkit.dex`: Dex's image, accounts, config and `start_dex()`.
   - `testkit.dexflow`: moved verbatim.
   - `testkit.auth`: Auth's test settings.

   **Consequence:** `testkit` depends on `collabhub-auth`, because `dexflow` imports
   `auth.cookies` and `auth.pkce`, and `build_settings` builds `auth.settings.Settings`.
2. **`from tests …` becomes a lint error** through ruff TID251 banned-api. It was checked against
   ruff 0.16.0: the rule catches `from tests import x`, `from tests.conftest import x`,
   `import tests.integration.conftest` and `from tests.integration import x`, and ignores `bdd.*`
   and `testkit.*`.
3. **`Tokens`, the ASGI and uvicorn helpers, `truncate` and `RecordingServer` stay where they are
   until plan B.** Plan B rewrites those conftests for the shared containers, and moving them twice
   is waste.
4. **The plugin, not `test.sh`, sets `DOCKER_HOST=tcp://docker.invalid:1` for unit tests.** A bare
   `uv run pytest` then behaves exactly like the script.
5. **A layer marker that contradicts the directory stops the run.** The 16
   `pytestmark = pytest.mark.integration` lines are deleted. `test.sh` selects with `-m unit` and
   `-m integration`.
6. **The plugin's tests run pytest in a subprocess** (`pytester.runpytest_subprocess`). An
   in-process inner session would switch the socket guard off under the outer unit test. `pytester`
   is loaded for the whole workspace through `addopts = "-p pytester"`, because `pytest_plugins` is
   not allowed in a conftest below the rootdir.
7. **Framework and minimal rework only** (Elton, 2026-09-15). The worked example of decision #2,
   extracting `check_editable` and `check_deletable` from `messages.py` with their unit tests, is
   deferred to the backfill with every other new test for existing behaviour. No service's
   production code changes in this plan.
8. **Coverage runs on the unit layer only.** It measures the service packages with branch
   coverage and writes a terminal report plus `coverage.xml`, with no `--cov-fail-under`.

## What no unit test covers — read before approving red

- **That the move changed no behaviour.** It is proven by identical collection counts (Task 3) and a
  full `scripts/test.sh integration` run (Tasks 3 and 11), not by a new test.
- **That every Docker client obeys `DOCKER_HOST`.** The test pins the variable, not a failed
  ping. On this Mac `DOCKER_HOST` is unset and Docker Desktop is reached through a Docker context
  (`unix:///Users/elton/.docker/run/docker.sock`). docker-py's `from_env()` doesn't read contexts,
  so a ping from a unit test fails with or without the plugin and would prove nothing. docker-py
  and testcontainers both read `DOCKER_HOST` before any default, and nothing here tests them.
- **TID251.** It's configuration, not code. Task 2 proves it by running ruff on a scratch file.

## Global Constraints

- Python `>=3.12,<3.13`, and bash 3.2 for `scripts/`.
- Library floors, from the lock or PyPI on 2026-09-15:
  - `pytest>=9.1`
  - `pytest-socket>=0.8.1`
  - `pytest-cov>=7.1`
  - `testcontainers>=4.15`
  - `httpx>=0.28`
- New code imports testcontainers from `testcontainers.community.*` or `testcontainers.core.*`.
  The top-level `testcontainers.postgres` and `.redis` paths emit `DeprecationWarning` in 4.15.
- Run `uv sync --locked --all-packages` after any `pyproject.toml` change, and `uv lock` first when
  a dependency changes.
- `ruff check` and `ruff format` must be clean. The edit hook enforces this and blocks, so fix what
  it reports.
- Never `git add`, `git mv` or `git commit`.
- CLAUDE.md: `testkit` is dev-only, and no Dockerfile may install it. The Dockerfiles use
  `uv sync --locked --no-dev --package collabhub-<service>`, which already excludes it.

## File map

| Path | Change | Responsibility |
|---|---|---|
| `CLAUDE.md` | modify | working rule (Task 0); layout, stack and testing (Task 10) |
| `pyproject.toml` | modify | dev group, workspace source, `-p pytester`, markers, coverage config |
| `ruff.toml` | modify | `testkit` first-party, TID251 ban, testkit per-file ignores |
| `scripts/test.sh` | modify | `-m unit --cov …`, `-m integration` |
| `src/services/testkit/pyproject.toml` | create | the package and its `pytest11` entry point |
| `src/services/testkit/testkit/__init__.py` | create | package docstring |
| `src/services/testkit/testkit/plugin.py` | create | layer by directory; unit socket and Docker guard |
| `src/services/testkit/testkit/dex.py` | create | Dex's image, accounts, config, `start_dex()` |
| `src/services/testkit/testkit/auth.py` | create | Auth's test settings and `build_settings()` |
| `src/services/testkit/testkit/dexflow.py` | move from `src/services/auth/tests/dexflow.py` | unchanged |
| `src/services/testkit/tests/unit/test_plugin.py` | create | the plugin's rules, through `pytester` |
| `src/services/*/tests/{unit,integration}/` | move | every existing test and conftest (Task 3) |
| `src/services/auth/tests/integration/conftest.py` | modify | imports Dex and settings from `testkit` |
| `src/services/auth/tests/integration/test_{api,federation,members,refresh_cookie,users}.py` | modify | imports only |
| 16 integration test files | modify | delete `pytestmark = pytest.mark.integration` |
| `docs/design/00-platform-conventions.md` | modify | §11 |
| `docs/design/07-open-decisions-register.md` | modify | D32 row, settled line, D27 note |
| `docs/adr/260915-a-test-pyramid-with-journeys-at-the-top.md` | create | via `adr-writer` |

---

## Phase 0 — rules

### Task 0: Replace the unit-only rule in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`, the "Working in this repo" bullet that begins
  "**New behaviour is test-driven, with unit tests only — for now.**"

**Interfaces:** none.

- [ ] **Step 1: Replace the bullet**

Old (one line):

```markdown
- **New behaviour is test-driven, with unit tests only — for now.** Write the failing unit test first (pytest, no Docker — `scripts/test.sh unit`), run it, and **stop at red** so the tests can be reviewed before any production code is written. No new integration tests, no new steps, feature files or page objects in `tests/bdd`, and no frontend tests until that is widened. Say plainly what a unit test cannot reach rather than faking a database to reach it.
```

New (one line):

```markdown
- **New behaviour is test-driven, at the lowest layer that can prove it** (register D32). Write the failing test first — a unit test for a rule, a mapping or a wire shape; an integration test for SQL, a socket or a stream, against dependencies testcontainers starts; a `tests/bdd` scenario only for a key user journey — run it, and **stop at red** so the tests can be reviewed before any production code is written. Frontend unit tests wait for Vitest (`docs/plans/ch07/01-test-pyramid-design.md`, plan C). Never fake a database to reach SQL behaviour from a unit test.
```

- [ ] **Step 2: Leave uncommitted.**

---

## Phase 1 — restructure, staying green

### Task 1: Scaffold `testkit` and register it

**Files:**
- Create: `src/services/testkit/pyproject.toml`
- Create: `src/services/testkit/testkit/__init__.py`
- Create: `src/services/testkit/testkit/plugin.py`
- Modify: `pyproject.toml`
- Modify: `ruff.toml`

**Interfaces:**
- Produces: the importable package `testkit`; the entry point `pytest11: collabhub = testkit.plugin`;
  the `pytester` fixture in every run.

- [ ] **Step 1: Create `src/services/testkit/pyproject.toml`**

```toml
[project]
name = "collabhub-testkit"
version = "0.1.0"
description = "CollabHub's test harness: the pytest plugin that enforces the test layers, and the helpers services' tests share. Dev only — no image installs it."
requires-python = ">=3.12,<3.13"
dependencies = [
    # `dexflow` drives Auth's own routes and imports `auth.cookies` / `auth.pkce`,
    # and `testkit.auth` builds Auth's Settings.
    "collabhub-auth",
    "pytest>=9.1",
    "pytest-socket>=0.8.1",
    "httpx>=0.28",
    "testcontainers>=4.15",
]

# Loaded by every pytest run in the workspace, with no conftest import — which
# is the point: a conftest can only be shared by importing it, and every
# service's `tests` directory is the same namespace package.
[project.entry-points.pytest11]
collabhub = "testkit.plugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["testkit"]
```

- [ ] **Step 2: Create `src/services/testkit/testkit/__init__.py`**

```python
"""CollabHub's test harness (register D32).

`testkit.plugin` is loaded into every pytest run through the `pytest11` entry
point. The other modules are helpers a service's tests import by name —
`from testkit.dex import ADA` — because `from tests… import` is ambiguous in
this repo and banned by ruff (TID251).

Development only. It sits in the root `dev` dependency group, and no service
depends on it, so `uv sync --no-dev --package collabhub-<service>` in the
Dockerfiles never installs it.
"""
```

- [ ] **Step 3: Create `src/services/testkit/testkit/plugin.py` with a docstring only**

```python
"""CollabHub's pytest plugin. Empty until Task 6 of plan A gives it its rules."""
```

- [ ] **Step 4: Edit the root `pyproject.toml`**

In `[dependency-groups] dev`, add two entries after `"asyncpg>=0.30",`:

```toml
    "pytest-cov>=7.1",
    # The test harness and its pytest plugin. A dev dependency, not one of the
    # root's `dependencies`: it is a workspace member, but nothing ships it.
    "collabhub-testkit",
```

In `[tool.uv.sources]`, add after `collabhub-worker = { workspace = true }`:

```toml
collabhub-testkit = { workspace = true }
```

Replace `addopts = "--import-mode=importlib"` with the following. Keep the comment above it,
and add the second comment line:

```toml
# `-p pytester` because testkit's own tests need the fixture, and pytest refuses
# `pytest_plugins` in any conftest below the rootdir.
addopts = "--import-mode=importlib -p pytester"
```

- [ ] **Step 5: Edit `ruff.toml`**

Replace:

```toml
known-first-party = ["shared", "contracts", "auth", "messaging", "canvas", "asset", "worker"]
```

with:

```toml
known-first-party = ["shared", "contracts", "testkit", "auth", "messaging", "canvas", "asset", "worker"]
```

In `[lint.per-file-ignores]`, add after the `"tests/**"` line:

```toml
# The harness holds the same fixture credentials the tests do — Dex's password
# and client secret, the Worker's service secret — moved here from Auth's conftest.
"src/services/testkit/**" = ["T20", "S101", "S105", "S106"]
```

- [ ] **Step 6: Lock and sync**

Run: `cd /Users/elton/scm/manning/caw-test-pyramid && uv lock && uv sync --locked --all-packages`
Expected: `uv.lock` gains `collabhub-testkit`, `pytest-socket` and `pytest-cov`. No errors.

- [ ] **Step 7: Prove the entry point is registered**

Run: `uv run python -c "from importlib.metadata import entry_points; print([e.value for e in entry_points(group='pytest11') if e.name == 'collabhub'])"`
Expected: `['testkit.plugin']`

- [ ] **Step 8: Prove nothing moved**

Run: `uv run pytest --collect-only -q -m "not integration and not bdd" | tail -1`
Expected: `112/442 tests collected (330 deselected)`

Run: `uv run pytest -m "not integration and not bdd" -q | tail -1`
Expected: `112 passed`

- [ ] **Step 9: Leave uncommitted.**

---

### Task 2: Move Dex and Auth's test helpers into `testkit`, and ban `from tests`

**Files:**
- Create: `src/services/testkit/testkit/dex.py`
- Create: `src/services/testkit/testkit/auth.py`
- Move: `src/services/auth/tests/dexflow.py` → `src/services/testkit/testkit/dexflow.py`
- Modify: `src/services/auth/tests/conftest.py`
- Modify: `src/services/auth/tests/test_api.py`, `test_federation.py`, `test_members.py`,
  `test_refresh_cookie.py`, `test_users.py` (imports only)
- Modify: `ruff.toml`

**Interfaces:**
- Produces, in `testkit.dex`:
  - constants `DEX_IMAGE: str`, `DEX_PORT: int`, `DEX_CLIENT_ID: str`, `DEX_CLIENT_SECRET: str`,
    `DEX_PASSWORD: str`, `DEX_PASSWORD_HASH: str`, `ADA: str`, `GRACE: str`, `ALAN: str`,
    `ADA_NAME: str`
  - `start_dex(config_dir: Path, *, relying_party_issuer: str) -> AbstractContextManager[str]`,
    which yields the issuer URL
- Produces, in `testkit.auth`:
  - constants `AUTH_ISSUER: str`, `DEMO_WORKSPACE: str`, `SPA_REDIRECT: str`,
    `WORKER_SECRET: str`, `A_SIGNING_KEY: str`
  - `build_settings(postgres_dsn: str, redis_url: str, dex_issuer: str, **overrides: Any) -> auth.settings.Settings`
- Produces, in `testkit.dexflow`: the module's existing functions, unchanged: `authenticate`,
  `sign_in`, `begin`, `finish`, `issued_cookie`, `session_cookie`, `renewed`.

- [ ] **Step 1: Create `src/services/testkit/testkit/dex.py`**

This is Auth's conftest's Dex half, moved. Only `start_dex` is new: it wraps the old fixture body so
the fixture stays in Auth's conftest.

```python
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

# Kept in step with docs/platform/versions.md.
DEX_IMAGE = "ghcr.io/dexidp/dex:v2.45.1"
DEX_PORT = 15556

DEX_CLIENT_ID = "collabhub-auth"
DEX_CLIENT_SECRET = "test-client-secret"

# bcrypt of DEX_PASSWORD. Generated once and pinned rather than hashed at test
# setup, because bcrypt at cost 10 is deliberately slow and this is not what is
# being tested.
DEX_PASSWORD = "collabhub"
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
```

- [ ] **Step 2: Create `src/services/testkit/testkit/auth.py`**

```python
"""Auth's test configuration — the values its integration tests build the app with.

Here rather than in Auth's conftest because test modules import these by name,
and a conftest cannot be imported unambiguously: every service's `tests`
directory is the same namespace package.
"""

from __future__ import annotations

from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth.settings import Settings
from testkit.dex import DEX_CLIENT_ID, DEX_CLIENT_SECRET

# The issuer this service is configured with in tests, and the redirect URI Dex
# has registered — it has to match what the app builds from `auth_issuer`.
AUTH_ISSUER = "http://localhost:8001"

DEMO_WORKSPACE = "CollabHub Demo"
SPA_REDIRECT = "http://localhost:5173/auth/callback"
WORKER_SECRET = "worker-local-secret"

# Outside `local` the service refuses to invent a signing key, so any test that
# builds an app as if deployed has to supply one. Generated once per session —
# RSA keygen is slow enough to notice if every test did it.
A_SIGNING_KEY = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    .decode()
)


def build_settings(
    postgres_dsn: str, redis_url: str, dex_issuer: str, **overrides: Any
) -> Settings:
    """Public and internal authority are the same value here: the test process
    reaches Dex at the URL Dex calls itself, so there is nothing to translate.
    The split they exist for is unit-tested in test_oidc.py, which needs no
    container to prove a URL is rewritten.
    """
    values: dict[str, Any] = {
        "app_env": "local",
        "postgres_dsn": postgres_dsn,
        "redis_cache_url": redis_url,
        "auth_issuer": AUTH_ISSUER,
        "spa_redirect_uri": SPA_REDIRECT,
        "auth_demo_workspace_name": DEMO_WORKSPACE,
        "auth_service_clients": [
            {"client_id": "worker", "secret": WORKER_SECRET, "scopes": ["assets:write-variants"]}
        ],
        "oidc_providers": [
            {
                "name": "dex",
                "authority": dex_issuer,
                "internalAuthority": dex_issuer,
                "clientId": DEX_CLIENT_ID,
                "clientSecret": DEX_CLIENT_SECRET,
            }
        ],
    }
    values.update(overrides)
    return Settings(**values)
```

- [ ] **Step 3: Move `dexflow.py`**

Run: `mv src/services/auth/tests/dexflow.py src/services/testkit/testkit/dexflow.py`
Expected: no output. Content unchanged: it imports only `auth`, `httpx` and the stdlib.

- [ ] **Step 4: Replace `src/services/auth/tests/conftest.py`**

This is the whole new file. The fixtures below `dex_issuer` are unchanged from today.

```python
"""Real Postgres, Redis and Dex for the Auth service's integration tests.

One container of each per test session (Conventions §11 — testcontainers, not
mocks). Every test gets a clean database: rather than re-running migrations,
which is slow, the tables are truncated between tests.

**Dex is real too.** Sign-in is the one thing this service exists to do, and a
stubbed identity provider would test our idea of OIDC rather than OIDC. The
tests drive the actual redirect flow, through the actual login form, against the
image the compose stack runs. Dex's accounts and container live in
`testkit.dex`, and Auth's test settings in `testkit.auth`, so test modules can
import them by name.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from auth.main import create_app
from auth.migrations import upgrade_to_head
from auth.settings import Settings
from testkit.auth import AUTH_ISSUER, build_settings
from testkit.dex import start_dex

TABLES = "refresh_tokens, external_identities, workspace_members, workspaces, users"


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:18", driver="asyncpg") as container:
        dsn = container.get_connection_url()
        asyncio.run(upgrade_to_head(dsn))
        yield dsn


@pytest.fixture(scope="session")
def dex_issuer(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real Dex, configured for three local accounts. Yields its issuer URL."""
    with start_dex(tmp_path_factory.mktemp("dex"), relying_party_issuer=AUTH_ISSUER) as issuer:
        yield issuer


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:8") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def engine(postgres_dsn: str) -> AsyncIterator:
    engine = create_async_engine(postgres_dsn)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessions(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def app_settings(postgres_dsn: str, redis_url: str, dex_issuer: str) -> Settings:
    """The settings every integration test builds its app from."""
    return build_settings(postgres_dsn, redis_url, dex_issuer)


@pytest.fixture
async def client(app_settings: Settings, engine) -> AsyncIterator[httpx.AsyncClient]:
    """The Auth app on an ASGI transport, against the real containers."""
    app = create_app(app_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()
```

- [ ] **Step 5: Rewrite the imports in the five Auth test files**

`src/services/auth/tests/test_api.py`:
- Replace `from tests.conftest import ADA, DEMO_WORKSPACE, DEX_PASSWORD, GRACE, WORKER_SECRET, build_settings`
  with `from testkit.auth import DEMO_WORKSPACE, WORKER_SECRET, build_settings` and
  `from testkit.dex import ADA, DEX_PASSWORD, GRACE`.
- Replace `from tests.dexflow import renewed, session_cookie` with
  `from testkit.dexflow import renewed, session_cookie`.
- Replace `from tests import dexflow` with `from testkit import dexflow`.

`src/services/auth/tests/test_federation.py`:
- Replace the block `from tests.conftest import ( ADA, AUTH_ISSUER, DEMO_WORKSPACE, DEX_CLIENT_ID, DEX_PASSWORD, GRACE, SPA_REDIRECT, )`
  with `from testkit.auth import AUTH_ISSUER, DEMO_WORKSPACE, SPA_REDIRECT` and
  `from testkit.dex import ADA, DEX_CLIENT_ID, DEX_PASSWORD, GRACE`.
- Replace `from tests import dexflow` with `from testkit import dexflow`.

`src/services/auth/tests/test_members.py`:
- Replace `from tests.conftest import ADA, ALAN, DEMO_WORKSPACE, DEX_PASSWORD, GRACE` with
  `from testkit.auth import DEMO_WORKSPACE` and `from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE`.
- Replace `from tests.dexflow import renewed, session_cookie` with
  `from testkit.dexflow import renewed, session_cookie`.
- Replace `from tests import dexflow` with `from testkit import dexflow`.

`src/services/auth/tests/test_refresh_cookie.py`:
- Replace `from tests.conftest import ADA, DEMO_WORKSPACE, DEX_PASSWORD` with
  `from testkit.auth import DEMO_WORKSPACE` and `from testkit.dex import ADA, DEX_PASSWORD`.
- Replace `from tests.dexflow import session_cookie` with `from testkit.dexflow import session_cookie`.
- Replace `from tests import dexflow` with `from testkit import dexflow`.

`src/services/auth/tests/test_users.py`:
- Replace `from tests.conftest import A_SIGNING_KEY, ADA, ALAN, DEX_PASSWORD, GRACE, build_settings`
  with `from testkit.auth import A_SIGNING_KEY, build_settings` and
  `from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE`.
- Replace `from tests import dexflow` with `from testkit import dexflow`.

The edit hook's ruff `I` autofix re-sorts the import blocks. Accept its order.

- [ ] **Step 6: Ban `from tests` in `ruff.toml`**

In the `select` list, add after `"ERA",  # eradicate — commented-out code`:

```toml
    "TID251", # banned imports — see [lint.flake8-tidy-imports.banned-api]
```

Add a new section after `[lint.mccabe]`:

```toml
[lint.flake8-tidy-imports.banned-api]
# No service's `tests` directory has an `__init__.py`, so `tests` is one
# namespace package spanning all of them, and `from tests.conftest import X`
# binds to whichever service sorts first. Shared helpers live in `testkit`; a
# service's own go through fixtures.
"tests".msg = "`tests` spans every service's test directory — import shared helpers from `testkit`, or take a fixture"
```

- [ ] **Step 7: Prove the ban bites and the tree is clean**

Run:

```bash
S=/private/tmp/claude-501/-Users-elton-scm-manning-caw-project/479435a7-6572-42ca-ba0b-877342f4ab69/scratchpad
printf 'from tests.conftest import ADA\n' > "$S/test_ban.py"
uv run ruff check --no-cache --config ruff.toml "$S/test_ban.py"
```

Expected: `TID251 `tests` is banned: …`, exit 1.

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: `All checks passed!` and no files to reformat.

- [ ] **Step 8: Prove Auth's suite is unchanged**

Run: `uv run pytest --collect-only -q -m "integration and not bdd" src/services/auth | tail -1`
Expected: `105/148 tests collected (43 deselected)`, which is 105 integration tests plus Auth's 43
unit tests deselected.

Run: `scripts/test.sh integration -- src/services/auth`
Expected: `105 passed`, and `==> passed: integration`.

- [ ] **Step 9: Leave uncommitted.**

---

### Task 3: Move every service test into `unit/` or `integration/`

**Files:**
- Move: see Step 1. The layer of each file is the one it is collected in today; no file holds
  both.

**Interfaces:**
- Produces: the layout the plugin (Task 6) enforces:
  `src/services/<service>/tests/{unit,integration}/`.

- [ ] **Step 1: Move the files with `mv`, not `git mv`**

```bash
cd /Users/elton/scm/manning/caw-test-pyramid/src/services
for s in shared auth messaging canvas asset worker; do mkdir -p "$s/tests/unit"; done
for s in shared auth messaging; do mkdir -p "$s/tests/integration"; done

mv shared/tests/test_cors.py shared/tests/test_health.py shared/tests/test_ids.py \
   shared/tests/test_keys.py shared/tests/test_pagination.py shared/tests/test_problems.py \
   shared/tests/unit/
mv shared/tests/conftest.py shared/tests/test_denylist.py shared/tests/test_security.py \
   shared/tests/integration/

mv auth/tests/test_health.py auth/tests/test_oidc.py auth/tests/test_signing_keys.py \
   auth/tests/test_tokens.py auth/tests/unit/
mv auth/tests/conftest.py auth/tests/test_api.py auth/tests/test_federation.py \
   auth/tests/test_members.py auth/tests/test_refresh_cookie.py auth/tests/test_schema.py \
   auth/tests/test_users.py auth/tests/integration/

mv messaging/tests/test_health.py messaging/tests/test_read_markers.py messaging/tests/unit/
mv messaging/tests/conftest.py messaging/tests/test_channels.py messaging/tests/test_members.py \
   messaging/tests/test_messages.py messaging/tests/test_pagination.py \
   messaging/tests/test_realtime.py messaging/tests/test_realtime_writes.py \
   messaging/tests/test_schema.py messaging/tests/test_tenancy.py messaging/tests/integration/

mv canvas/tests/test_health.py canvas/tests/unit/
mv asset/tests/test_health.py asset/tests/unit/
mv worker/tests/test_health.py worker/tests/unit/

# Stale bytecode from the old paths would otherwise sit beside the new folders.
find . -path '*/tests/__pycache__' -prune -exec rm -rf {} +
```

- [ ] **Step 2: Confirm nothing is left directly in a service's `tests/`**

Run: `find src/services -path '*/tests/*' -type f -not -path '*/__pycache__/*' | grep -v -E '/tests/(unit|integration)/'`
(from the worktree root)
Expected: no output.

- [ ] **Step 3: Fix references to the old paths in live files**

Run: `grep -rn -E 'services/[a-z]+/tests/(test_|conftest|dexflow)' --include='*.py' --include='*.md' --include='*.sh' --include='*.toml' --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.git . | grep -v -E '^\./docs/(plans|adr)/'`

For each hit, change the path to its new `unit/` or `integration/` location, or to
`src/services/testkit/testkit/dexflow.py`. Leave `docs/plans/` and `docs/adr/` alone: they record
what was true when they were written.
Expected after edits: the command prints nothing.

- [ ] **Step 4: Prove the counts are unchanged**

Run:

```bash
for m in "not integration and not bdd" "integration and not bdd" "bdd"; do
  uv run pytest --collect-only -q -m "$m" | tail -1
done
```

Expected, in order:
- `112/442 tests collected (330 deselected)`
- `287/442 tests collected (155 deselected)`
- `43/442 tests collected (399 deselected)`

- [ ] **Step 5: Prove the moved tests pass**

Run: `scripts/test.sh unit integration`
Expected: `112 passed`, then `287 passed`, then `==> passed: unit integration`.

- [ ] **Step 6: Leave uncommitted.**

---

## Phase 2 — RED

### Task 4: Write the plugin's tests

**Files:**
- Create: `src/services/testkit/tests/unit/test_plugin.py`

**Interfaces:**
- Consumes: `pytester` (Task 1); the entry point `testkit.plugin` (Task 1).
- Pins, for Task 6:
  - Markers `unit` and `integration`, added to items under `src/services/<svc>/tests/unit/` and
    `…/tests/integration/`.
  - `pytest.UsageError` text containing `is not under tests/unit/ or tests/integration/`.
  - `pytest.UsageError` text containing `is marked integration but lives under tests/unit/`.
  - `DOCKER_HOST=tcp://docker.invalid:1` and sockets blocked apart from `AF_UNIX`, for unit items
    only.

- [ ] **Step 1: Create the test file**

```python
"""The layer rules `testkit.plugin` enforces (register D32).

Each test lays out a throwaway repo under pytester's temp directory and runs
pytest on it **in a subprocess**. In-process, the inner session's socket guard
would run inside this unit test's own, and the inner teardown would switch the
network back on under the outer test.
"""

from __future__ import annotations

import textwrap

import pytest

DEMO = "src/services/demo/tests"


@pytest.fixture
def repo(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    """A repo root the plugin measures `src/services/...` from.

    The ini file pins pytest's rootdir to it. `DOCKER_HOST` is cleared because
    this outer test runs as a unit test too, and the subprocess inherits its
    environment: the dead address the outer plugin set would make the inner
    Docker test pass without the inner plugin doing anything.
    """
    pytester.makeini("[pytest]\naddopts = --import-mode=importlib\n")
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    return pytester


def write(pytester: pytest.Pytester, path: str, source: str) -> None:
    target = pytester.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(source))


def run(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    return pytester.runpytest_subprocess(*args, timeout=60)


PASSING = """
def test_it():
    pass
"""


# --- the directory decides the layer ---------------------------------------


def test_a_test_under_unit_is_selected_by_the_unit_marker(repo):
    """Breaks if the plugin does not mark `tests/unit/` as `unit`."""
    write(repo, f"{DEMO}/unit/test_a.py", PASSING)

    run(repo, "-m", "unit").assert_outcomes(passed=1)


def test_a_test_under_integration_is_selected_by_the_integration_marker(repo):
    """Breaks if the plugin does not mark `tests/integration/` as `integration`,
    or marks it `unit` as well."""
    write(repo, f"{DEMO}/integration/test_a.py", PASSING)

    run(repo, "-m", "integration and not unit").assert_outcomes(passed=1)


def test_a_test_outside_both_layers_stops_the_run(repo):
    """The old failure: a file that forgot its marker ran as a unit test.

    Breaks if a stray file is collected at all, or the message does not say
    which file and where it should go.
    """
    write(repo, f"{DEMO}/test_stray.py", PASSING)

    result = run(repo)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(
        ["*src/services/demo/tests/test_stray.py is not under tests/unit/ or tests/integration/*"]
    )


def test_a_marker_that_contradicts_the_directory_stops_the_run(repo):
    """Breaks if an `integration` marker can smuggle a test into the unit
    directory — the file has to move instead."""
    write(
        repo,
        f"{DEMO}/unit/test_a.py",
        """
        import pytest

        pytestmark = pytest.mark.integration

        def test_it():
            pass
        """,
    )

    result = run(repo)

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*test_a.py is marked integration but lives under tests/unit/*"])


def test_tests_outside_src_services_are_left_alone(repo):
    """The Gherkin suite at `tests/bdd` belongs to neither layer.

    Breaks if the plugin errors on it or marks it. Passes before the plugin
    exists — it guards against an implementation that is too eager.
    """
    write(repo, "tests/bdd/test_journey.py", PASSING)

    run(repo, "-m", "not unit and not integration").assert_outcomes(passed=1)


# --- a unit test has no network and no Docker -------------------------------


def test_a_unit_test_cannot_open_a_network_socket(repo):
    """Breaks if a unit test can create an AF_INET socket."""
    write(
        repo,
        f"{DEMO}/unit/test_dial.py",
        """
        import socket

        def test_it():
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        """,
    )

    result = run(repo)

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*SocketBlockedError*"])


def test_a_unit_test_can_still_run_an_event_loop(repo):
    """asyncio's self-pipe is an AF_UNIX socketpair.

    Breaks if the guard blocks Unix sockets, which would fail every async unit
    test. Passes before the plugin exists.
    """
    write(
        repo,
        f"{DEMO}/unit/test_loop.py",
        """
        import asyncio

        def test_it():
            asyncio.run(asyncio.sleep(0))
        """,
    )

    run(repo).assert_outcomes(passed=1)


def test_a_unit_test_points_docker_clients_at_an_unreachable_host(repo):
    """Docker's default transport is a Unix socket, which the socket guard allows.

    Pins `DOCKER_HOST` rather than attempting a ping. Docker clients read it
    before any default, and a ping is no proof on Docker Desktop: it is reached
    through a Docker context that docker-py's `from_env()` never reads, so the
    ping fails with or without this plugin.

    Breaks if a unit test runs with `DOCKER_HOST` unset or pointing anywhere
    else.
    """
    write(
        repo,
        f"{DEMO}/unit/test_docker.py",
        """
        import os

        def test_it():
            assert os.environ.get("DOCKER_HOST") == "tcp://docker.invalid:1"
        """,
    )

    run(repo).assert_outcomes(passed=1)


def test_an_integration_test_can_open_a_network_socket(repo):
    """Breaks if the guard leaks into the integration layer. Passes before the
    plugin exists."""
    write(
        repo,
        f"{DEMO}/integration/test_dial.py",
        """
        import socket

        def test_it():
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        """,
    )

    run(repo).assert_outcomes(passed=1)


def test_the_network_comes_back_after_a_unit_test(repo):
    """`demo` sorts before `zeta`, so the unit test runs first.

    Breaks if teardown leaves sockets blocked for the integration test after
    it. Passes before the plugin exists.
    """
    write(repo, f"{DEMO}/unit/test_a.py", PASSING)
    write(
        repo,
        "src/services/zeta/tests/integration/test_dial.py",
        """
        import socket

        def test_it():
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        """,
    )

    run(repo).assert_outcomes(passed=2)
```

- [ ] **Step 2: Leave uncommitted.**

---

### Task 5: Run them red, then STOP

- [ ] **Step 1: Run the plugin tests**

Run: `uv run pytest src/services/testkit -v`

Expected, because `testkit/plugin.py` is still only a docstring:

| Test | Result | Why |
|---|---|---|
| `test_a_test_under_unit_is_selected_by_the_unit_marker` | **FAIL** | `-m unit` selects nothing, so `assert_outcomes` sees 0 passed |
| `test_a_test_under_integration_is_selected_by_the_integration_marker` | **FAIL** | same |
| `test_a_test_outside_both_layers_stops_the_run` | **FAIL** | exit code 0, not 4 |
| `test_a_marker_that_contradicts_the_directory_stops_the_run` | **FAIL** | exit code 0, not 4 |
| `test_tests_outside_src_services_are_left_alone` | pass | guard |
| `test_a_unit_test_cannot_open_a_network_socket` | **FAIL** | the socket opens, so 1 passed, not 1 failed |
| `test_a_unit_test_can_still_run_an_event_loop` | pass | guard |
| `test_a_unit_test_points_docker_clients_at_an_unreachable_host` | **FAIL** | `DOCKER_HOST` is unset (the outer fixture clears it), so the inner assertion fails |
| `test_an_integration_test_can_open_a_network_socket` | pass | guard |
| `test_the_network_comes_back_after_a_unit_test` | pass | guard |

Summary line: `6 failed, 4 passed`.

- [ ] **Step 2: Confirm nothing else broke**

Run: `uv run pytest -m "not integration and not bdd" -q | tail -1`
Expected: `6 failed, 116 passed`. That is the 112 existing tests plus the 4 guards.

- [ ] **Step 3: STOP.** Report the run to Elton, with the red table above, and wait for review.
  Do not start Task 6 until he approves.

---

## Phase 3 — GREEN

### Task 6: The plugin → `test_plugin.py`

**Files:**
- Modify: `src/services/testkit/testkit/plugin.py`

**Interfaces:**
- Consumes: `pytest_socket.disable_socket(allow_unix_socket: bool)` and
  `pytest_socket.enable_socket()`, which are public in 0.8.1.
- Produces: markers `unit` and `integration`; `layer_of(path: Path, root: Path) -> str | None`.

- [ ] **Step 1: Replace `plugin.py`**

```python
"""CollabHub's pytest plugin: the directory decides a test's layer (register D32).

Registered through the `pytest11` entry point in testkit's pyproject, so every
pytest run in the workspace loads it without a conftest import.

Under `src/services/<service>/tests/`, a test in `unit/` is marked `unit` and
one in `integration/` is marked `integration`. A test anywhere else there stops
the run. Before this the layer was a `pytestmark` line, and a file that forgot
it ran in the unit layer, reaching for containers it had no business with.

A unit test gets no network and no Docker. Sockets other than Unix-domain ones
are refused — asyncio's self-pipe is an AF_UNIX socketpair, so an event loop
still works — and `DOCKER_HOST` points at an address that cannot resolve,
because the Docker SDK's default is a Unix socket the guard would let through.

Paths outside `src/services` — the Gherkin suite in `tests/bdd` — are left alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_socket import disable_socket, enable_socket

UNIT = "unit"
INTEGRATION = "integration"
LAYERS = (UNIT, INTEGRATION)
UNREACHABLE_DOCKER = "tcp://docker.invalid:1"

_environment = pytest.StashKey[pytest.MonkeyPatch]()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "unit: no network, no Docker — set by living in a service's tests/unit/"
    )
    config.addinivalue_line(
        "markers",
        "integration: real dependencies started by testcontainers — set by living in tests/integration/",
    )


def layer_of(path: Path, root: Path) -> str | None:
    """`unit` or `integration` for a test in a service's tests, None outside them.

    Raises `pytest.UsageError` for a test file in a service's `tests/` that is
    in neither layer's directory.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return None
    if len(parts) < 5 or parts[:2] != ("src", "services") or parts[3] != "tests":
        return None
    if len(parts) > 5 and parts[4] in LAYERS:
        return parts[4]
    raise pytest.UsageError(
        f"{Path(*parts)} is not under tests/unit/ or tests/integration/"
        " — the directory decides a test's layer."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        layer = layer_of(item.path, config.rootpath)
        if layer is None:
            continue
        for other in LAYERS:
            if other != layer and item.get_closest_marker(other):
                raise pytest.UsageError(
                    f"{item.path.relative_to(config.rootpath)} is marked {other} but lives"
                    f" under tests/{layer}/ — move the file rather than marking it."
                )
        item.add_marker(layer)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    # tryfirst, so the guard is up before the item's fixtures are set up — a
    # unit fixture that dials out fails as surely as the test would.
    if item.get_closest_marker(UNIT) is None:
        return
    environment = pytest.MonkeyPatch()
    environment.setenv("DOCKER_HOST", UNREACHABLE_DOCKER)
    item.stash[_environment] = environment
    disable_socket(allow_unix_socket=True)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    # trylast, so it runs after fixture teardown and undoes the guard outermost —
    # after a test's own monkeypatch has undone its changes.
    environment = item.stash.get(_environment, None)
    if environment is None:
        return
    enable_socket()
    environment.undo()
```

- [ ] **Step 2: Run the plugin tests**

Run: `uv run pytest src/services/testkit -v`
Expected: `11 passed`.

> **Fix round 1 (task review, 2026-09-15).** The teardown hook first shipped without `trylast`.
> A unit test's own `monkeypatch` of `DOCKER_HOST` then re-applied the dead address after the
> plugin's undo, and it leaked into later tests in the same process. A regression test,
> `test_docker_host_comes_back_after_a_unit_test_that_patches_it`, was added to `test_plugin.py`
> red first, and then the hook gained `trylast=True`. It is the 11th plugin test, and Elton saw
> it in the final report rather than at red.

- [ ] **Step 3: Run the unit layer**

Run: `uv run pytest -m unit -q | tail -1`
Expected: `123 passed`, which is 112 + 11.

- [ ] **Step 4: Leave uncommitted.**

---

### Task 7: Select layers by directory, not by `pytestmark`

**Files:**
- Modify: the 16 files listed in Step 1
- Modify: `pyproject.toml`
- Modify: `scripts/test.sh`

**Interfaces:**
- Consumes: the `unit` and `integration` markers from Task 6.

- [ ] **Step 1: Delete the redundant markers**

Delete the line `pytestmark = pytest.mark.integration`, and one blank line beside it, from each of
these files:
- `src/services/auth/tests/integration/test_api.py`
- `src/services/auth/tests/integration/test_federation.py`
- `src/services/auth/tests/integration/test_refresh_cookie.py`
- `src/services/auth/tests/integration/test_users.py`
- `src/services/auth/tests/integration/test_members.py`
- `src/services/auth/tests/integration/test_schema.py`
- `src/services/messaging/tests/integration/test_tenancy.py`
- `src/services/messaging/tests/integration/test_members.py`
- `src/services/messaging/tests/integration/test_channels.py`
- `src/services/messaging/tests/integration/test_pagination.py`
- `src/services/messaging/tests/integration/test_realtime.py`
- `src/services/messaging/tests/integration/test_schema.py`
- `src/services/messaging/tests/integration/test_messages.py`
- `src/services/messaging/tests/integration/test_realtime_writes.py`
- `src/services/shared/tests/integration/test_denylist.py`
- `src/services/shared/tests/integration/test_security.py`

If `pytest` is then unused in a file, the edit hook's ruff `F401` autofix removes the import.
Accept that.

- [ ] **Step 2: Update the markers in `pyproject.toml`**

Replace these lines:

```toml
# Integration tests start real Postgres/Redis containers (Conventions §11), so
# they need Docker and take seconds rather than milliseconds. Run the fast ones
# alone with `uv run pytest -m "not integration"`.
#
```

with:

```toml
# `unit` and `integration` are not declared here: testkit's plugin registers
# them and sets them from the directory a test lives in (register D32).
#
```

Delete this entry from `markers`:

```toml
    "integration: needs Docker; starts real backing services",
```

- [ ] **Step 3: Update `scripts/test.sh`**

Replace:

```bash
    uv run pytest -m "not integration and not bdd" ${pytest_args[@]+"${pytest_args[@]}"}
```

with:

```bash
    uv run pytest -m unit ${pytest_args[@]+"${pytest_args[@]}"}
```

Replace:

```bash
    uv run pytest -m "integration and not bdd" ${pytest_args[@]+"${pytest_args[@]}"}
```

with:

```bash
    uv run pytest -m integration ${pytest_args[@]+"${pytest_args[@]}"}
```

- [ ] **Step 4: Prove every test belongs to exactly one selection**

Run:

```bash
for m in unit integration bdd "not unit and not integration and not bdd"; do
  uv run pytest --collect-only -q -m "$m" | tail -1
done
```

Expected, in order:
- `123/453 tests collected (330 deselected)`
- `287/453 tests collected (166 deselected)`
- `43/453 tests collected (410 deselected)`
- `no tests collected (453 deselected)`

- [ ] **Step 5: Leave uncommitted.**

---

### Task 8: Coverage on the unit layer

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/test.sh`

**Interfaces:** none. This is configuration, verified by running it.

- [ ] **Step 1: Add coverage config to the end of `pyproject.toml`**

```toml
# Reported on the unit layer, not gated (register D32): a floor is set once the
# backfill has measured one. The service packages only — not their tests, not
# testkit, not Alembic revisions.
[tool.coverage.run]
source_pkgs = ["shared", "contracts", "auth", "messaging", "canvas", "asset", "worker"]
branch = true
omit = ["*/alembic/*"]

[tool.coverage.report]
skip_empty = true
```

- [ ] **Step 2: Report coverage from `scripts/test.sh unit`**

Replace:

```bash
    uv run pytest -m unit ${pytest_args[@]+"${pytest_args[@]}"}
```

with:

```bash
    uv run pytest -m unit --cov --cov-report=term:skip-covered --cov-report=xml \
        ${pytest_args[@]+"${pytest_args[@]}"}
```

- [ ] **Step 3: Run it**

Run: `scripts/test.sh unit`
Expected: `123 passed`, then a coverage table with a `TOTAL` row. `coverage.xml` is written at the
repo root and ignored by git (it's already in `.gitignore`). The run ends with
`==> passed: unit`.

- [ ] **Step 4: Leave uncommitted.**

---

## Phase 4 — REFACTOR

### Task 9: Tidy, staying green

- [ ] **Step 1:** Read the diff of `plugin.py`, `dex.py`, `auth.py` and the Auth
  conftest. Look for leftovers:
  - an unused import
  - a docstring that still names `tests/dexflow.py` or `tests/conftest.py`
  - the Messaging conftest's `from tests.conftest` warnings, which should now point at `testkit` and
    TID251
- [ ] **Step 2:** Run `uv run ruff check . && uv run ruff format --check .`. Expected: clean.
- [ ] **Step 3:** Run `scripts/test.sh unit`. Expected: `123 passed`.
- [ ] **Step 4:** Leave uncommitted.

---

## Finish

### Task 10: Record the decision in this slice

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/design/00-platform-conventions.md` §11
- Modify: `docs/design/07-open-decisions-register.md`
- Create: `docs/adr/260915-a-test-pyramid-with-journeys-at-the-top.md`

- [ ] **Step 1: CLAUDE.md, the repo layout**

Replace `src/services/{shared,contracts,auth,messaging,canvas,asset,worker}` with
`src/services/{shared,contracts,testkit,auth,messaging,canvas,asset,worker}`.

Replace the paragraph that begins "Per-service tests live beside their service" and ends
"(`pythonpath = ["tests"]`)." with:

```markdown
Per-service tests live beside their service, in `src/services/*/tests/unit/` and
`tests/integration/`. **The directory decides the layer**: `testkit`'s pytest
plugin marks each test by where it lives, stops the run for a test anywhere else,
and cuts unit tests off from the network and Docker. Only the Gherkin suite is at
the root, because it spans every service at once.

No service's `tests` directory has an `__init__.py`, so `tests` is one namespace
package spanning all of them and `from tests.… import` binds to whichever sorts
first — ruff bans it (TID251). Shared helpers live in `src/services/testkit`, a
dev-only workspace member no image installs; a service's own go through fixtures.
The root suite avoids the clash by being importable as `bdd.*` (`pythonpath = ["tests"]`).
```

- [ ] **Step 2: CLAUDE.md, Stack decisions**

Replace:

```markdown
- **pytest** with **testcontainers-python** for integration tests (real Postgres/Redis/Garage/Elasticsearch, not mocks).
```

with:

```markdown
- **pytest** with **testcontainers-python** for integration tests — every dependency (Postgres, Redis, Elasticsearch, Garage, Dex) is started by testcontainers, never the Compose stack. Unit tests have no network and no Docker (pytest-socket, applied by `testkit`). **pytest-cov** reports unit coverage; nothing gates on it yet. The layers are register D32.
```

- [ ] **Step 3: CLAUDE.md, Testing**

Replace:

```markdown
**New tests are unit tests, written first** — see Working in this repo. The
commands below run every suite; only the unit layer is growing at the moment.
```

with:

```markdown
**A test pyramid** (D32), and the failing test goes at the lowest layer that can
prove the behaviour — see Working in this repo.

- **Unit** — every rule, mapping and wire shape. No network, no Docker. A rule
  that sits behind a database fetch is made testable by pulling the decision into
  a pure function over the loaded row, never by faking a repository or a session.
- **Integration** — each service at its public boundary (REST, Socket.IO, a
  stream consumer), in-process, against dependencies testcontainers starts. SQL
  behaviour is proven here.
- **End-to-end** — `tests/bdd`, key user journeys only. A field rule belongs lower down.
```

Replace `scripts/test.sh unit             # fast, no Docker` with
`scripts/test.sh unit             # fast, no network or Docker; prints coverage`.

- [ ] **Step 4: Conventions §11**

In `docs/design/00-platform-conventions.md`, replace the bullet that begins
"- Test layers (pytest): unit (domain logic), integration" and ends "work together." with:

```markdown
- Test layers (register D32) — a pyramid, and a new test goes at the lowest layer that can
  prove the behaviour:
  - **Unit** (pytest, Vitest for the SPA): every rule, mapping and wire shape, with no network
    and no Docker. Contract tests are unit tests — both sides of a job are checked against the
    Pydantic models in `collabhub-contracts`. Rules behind a database fetch become pure
    functions over the loaded row; repositories and sessions are never faked.
  - **Integration** (pytest + testcontainers-python): one service at its public boundary —
    REST, Socket.IO, a stream consumer — in-process, against Postgres/Redis/Garage/ES/Dex
    that testcontainers starts. It stops at the service boundary; tokens are minted locally
    rather than fetched from Auth.
  - **End-to-end** — Gherkin scenarios in `tests/bdd` driving a real browser through the whole
    stack with pytest-bdd and Playwright (register D27), for **key user journeys only**. It is
    what proves CORS, the SPA's baked-in environment variables, a migration running on
    container start, and the OIDC redirect chain actually work together.
- A service's tests live in `tests/unit/` and `tests/integration/`, and the directory decides
  the layer: the `collabhub-testkit` pytest plugin marks each test by it and refuses a test
  anywhere else.
```

- [ ] **Step 5: Register — the D32 row**

In `docs/design/07-open-decisions-register.md`, add this row after the `| D30 |` row in the
*Frontend SPA* table:

```markdown
| D32 | Test strategy: what each layer is for (raised 2026-09-15; the docs listed four layers and no rule for choosing between them) | 🟢 **Decided (2026-09-15):** a test pyramid — unit tests for all functionality, integration tests for each service's public boundary against dependencies testcontainers starts, BDD for key user journeys only | The directory decides the layer (`tests/unit/`, `tests/integration/`), enforced by the `testkit` pytest plugin, which also cuts unit tests off from the network and Docker. Rules become pure functions; nothing fakes a repository. Contract tests fold into unit; the SPA gets Vitest. See [ADR 260915](../adr/260915-a-test-pyramid-with-journeys-at-the-top.md) and [the design](../plans/ch07/01-test-pyramid-design.md) | Cross-cutting (every service, Frontend, testing) |
```

- [ ] **Step 6: Register — the settled line and D27**

After the paragraph
`**Settled 2026-09-15:** D31 — read state follows channel *visibility*, …[ADR](../adr/260915-read-state-follows-channel-visibility.md).`
add:

```markdown
**Settled 2026-09-15:** D32 — a test pyramid: unit tests for every rule, integration tests for
each service's boundary against testcontainers, BDD for key journeys only.
[ADR](../adr/260915-a-test-pyramid-with-journeys-at-the-top.md).
```

In the `| D27 |` row's fourth cell, after
`See [ADR 260815](../adr/260815-pytest-bdd-and-playwright-for-acceptance-tests.md)`, append:
` Narrowed by D32 (2026-09-15) to key user journeys.`

- [ ] **Step 7: The ADR**

Invoke the `adr-writer` skill with this decision. Target file:
`docs/adr/260915-a-test-pyramid-with-journeys-at-the-top.md`.

- **Decision:** a standard test pyramid. Unit tests for all functionality, integration tests for
  each service's public boundary against dependencies testcontainers starts, BDD for key user
  journeys only.
- **Context:**
  - On `fe345be` the suite was inverted: 112 unit, 287 integration, 43 BDD.
  - Rules were reachable only through the database.
  - A missing marker silently made a test "unit".
  - Three conftests were copied.
  - The Worker, search and the SPA had no tests.
  - Half the BDD scenarios restated field rules.
  - Conventions §11 listed four layers with no rule for choosing between them.
- **Consequences:**
  - The directory decides the layer, and the `testkit` pytest plugin enforces that.
  - Unit tests have no network or Docker.
  - `from tests` is banned, and `testkit` depends on `collabhub-auth`.
  - Rules are extracted as pure functions when a slice touches a module.
  - Contract tests fold into unit.
  - The BDD suite shrinks to about 16 journeys, and each scenario is removed only with its
    replacement lower down.
  - `test.sh` gains an `e2e` layer in plan D. This supersedes ADR 260914's "the Gherkin suite is
    not included".
  - Coverage is reported, not gated.
- **Alternatives considered:**
  - **Repository protocols with in-memory fakes.** Rejected: a second implementation of every
    query that drifts from the first, and CLAUDE.md forbids faking the database.
  - **Keeping marker-selected layers.** Rejected: that is the silent-default failure.
  - **Contract testing as a fourth layer (Pact-style).** Rejected: one repo and one `contracts`
    package make it a unit concern.
  - **A frontend integration layer.** Rejected: covered from both sides.
  - **Playwright's TypeScript runner for e2e.** Already rejected in ADR 260815.

- [ ] **Step 8: Leave uncommitted.**

---

### Task 11: Verify everything

- [ ] **Step 1: Run everything CI runs**

Run: `scripts/test.sh`
Expected:
- lint clean
- `123 passed` with a coverage table
- `287 passed`
- `==> passed: lint unit integration`

- [ ] **Step 2: Confirm the working tree is unstaged**

Run: `git status --short | head -40 && git diff --cached --stat`
Expected:
- Deleted old test paths show as ` D`, new directories as `??`, modified files as ` M`.
- The `--cached` stat is **empty**.

- [ ] **Step 3: Report to Elton**

Tell him:
- the branch and worktree
- the counts before and after (112/287/43 → 123/287/43)
- the coverage `TOTAL`
- which records changed

Leave everything uncommitted.

---

## Not in this plan

- **Plan B (containers):**
  - one Postgres with a database per service
  - one Redis with a database index per role
  - Elasticsearch and Garage fixtures
  - `images.py` and its drift test
  - `Tokens`, `apps`, `db`, `RecordingServer` into `testkit`
  - Messaging's deprecated `testcontainers.postgres` and `.redis` imports
  - the Worker's `run_consumer`
- **Plan C:** Vitest for the SPA.
- **Plan D:** `scripts/test.sh e2e` and the README's acceptance-test section.
- **The backfill:**
  - the first worked example of decision #2: `check_editable` and `check_deletable` in
    `messages.py`, with their unit tests
  - Worker and search tests
  - SPA component tests
  - unit tests for rules still reachable only through integration tests (for example
    `validate_name`)
- **The BDD triage.**
