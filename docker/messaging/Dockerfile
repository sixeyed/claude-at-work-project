# syntax=docker/dockerfile:1
# CollabHub messaging service.
# Build context is the repo root — the uv lockfile is a workspace-wide artefact,
# so the whole src/services tree has to be present for `uv sync --locked` to
# resolve. Trade-off: a change in any service busts every service's build cache.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/services/ src/services/

# --no-editable so the venv is self-contained and the source tree can be dropped.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package collabhub-messaging

FROM python:3.12-slim

# Nothing in the image is baked with config; it all arrives as env vars
# (Conventions §8).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# The Alembic scripts live inside the `messaging` package, so they are already
# in the venv — nothing to copy, and nothing for the entrypoint to find at a
# path.
COPY --chown=app:app docker/messaging/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
USER app

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "messaging.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
