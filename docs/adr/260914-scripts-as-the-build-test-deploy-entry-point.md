# Bash scripts as the single entry point for build, test and deploy

- **Status:** Accepted
- **Date:** 2026-09-14

## Context

Until now CollabHub had no scripts. Every command a developer ran — `uv run
pytest` with the right markers, `ruff check` and `ruff format --check`, `docker
compose` with two files layered, `helm lint` — lived in the README, typed out by
hand. A CI pipeline was coming, and it would have had to copy those commands a
second time into a workflow file, where they would drift from the README the first
time either changed.

Builds were already split. Compose builds images under its own project names
(`collabhub-auth`, and `collabhub-test-auth` for the acceptance stack), while the
Helm chart expected `collabhub/<component>:<appVersion>`. Nothing connected the
two, so there was no single answer to "which image is this?"

The team works on macOS, where the system bash is 3.2, and CI runners are Linux.
Docker, Helm, k3d and kubectl are command-line tools, so most of the work is
sequencing them rather than computing anything.

## Decision

We will have three bash scripts in `scripts/` — `build.sh`, `test.sh` and
`deploy.sh` — and they are the only way to build images, run the checks and
deploy. **CI calls exactly the same scripts a developer does.** A step that exists
only in a pipeline file, or only in the README, is a bug.

- `build.sh [component...] [--push]` builds `docker/<component>/Dockerfile` and
  tags `${IMAGE_REGISTRY}/collabhub/<component>:${IMAGE_TAG}`. The tag defaults to
  the short commit SHA, with `-dirty` added when the worktree has uncommitted
  changes, and is never `latest`.
- `test.sh [lint|unit|integration]` runs ruff, the convention checks, eslint, tsc
  and `helm lint`, then the unit and integration pytest suites. Anything after
  `--` goes to pytest. The Gherkin suite is not included; it needs a stack brought
  up first.
- `deploy.sh [up|cluster|infra|app|status|down]` installs the Helm charts into the
  local k3d cluster — see
  [ADR 260914](260914-local-kubernetes-on-k3d-with-a-dev-only-dependency-chart.md).

The scripts share `scripts/lib/common.sh`, which owns the component list, image
naming and tagging. Everything a pipeline may need to change is an environment
variable with a local default — `IMAGE_REGISTRY`, `IMAGE_TAG`, `KUBE_CONTEXT` —
documented in `.env.example`. They are written for bash 3.2.

## Consequences

There is now one definition of each operation. The README and CLAUDE.md point at
the scripts instead of repeating commands, and a pipeline will be a thin sequence
of script calls plus whatever the CI platform needs for credentials and caching.
Image names and tags are computed in one place, so `build.sh` and `deploy.sh`
cannot disagree about which image a deploy means.

A `-dirty` tag is honest but not unique: two builds from the same dirty commit
share it. `deploy.sh` handles that by always pulling and restarting rollouts on a
dirty tag, and a pipeline building from a clean checkout never produces one.

Bash has real costs. Argument parsing is hand-rolled, error handling relies on
`set -euo pipefail` plus care, and bash 3.2 rules out associative arrays and needs
an awkward idiom for empty arrays. There are no tests for the scripts themselves,
and no `shellcheck` in the lint layer yet. If the scripts grow much beyond
sequencing tools, that is the signal to revisit.

`test.sh` runs `conventions.py` over every tracked Python file rather than only
what changed since HEAD, because in a CI checkout nothing has changed. The tree is
kept clean for exactly that reason.

## Alternatives Considered

### A Makefile

Make is on every macOS machine and CI runner and gives discoverable targets
(`make build`). It is a poor fit for what these scripts actually do — multi-step
logic, conditional restarts, registry checks, passing arbitrary arguments through
to pytest — which in Make turns into escaped shell inside recipes. A thin Makefile
over the scripts was also considered and rejected as a second layer to keep in step
for no new capability.

### A Python CLI run with uv

A `uv run collabhub build` command would get proper argument parsing and could be
tested with the existing pytest setup. But nearly every step shells out to docker,
helm, k3d or kubectl, and doing that from Python is more verbose and less legible
than the shell it wraps. It would also make `uv sync` a prerequisite for deploying,
which the deploy path does not otherwise need.

### Commands in the CI workflow file

Writing the steps straight into a pipeline definition is the default for most
projects. It leaves developers without a way to run what CI runs, and it is exactly
the second copy this decision exists to prevent.
