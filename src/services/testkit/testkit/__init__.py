"""CollabHub's test harness (register D32).

`testkit.plugin` is loaded into every pytest run through the `pytest11` entry
point. The other modules are helpers a service's tests import by name —
`from testkit.dex import ADA` — because `from tests… import` is ambiguous in
this repo and banned by ruff (TID251).

Development only. It sits in the root `dev` dependency group, and no service
depends on it, so `uv sync --no-dev --package collabhub-<service>` in the
Dockerfiles never installs it.
"""
