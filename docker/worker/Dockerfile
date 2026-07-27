# syntax=docker/dockerfile:1
# CollabHub Worker.
# Headless: no business HTTP, so no uvicorn command line — the process owns its
# own event loop and serves health from inside it (design doc 05 §2).

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/services/ src/services/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package collabhub-worker

FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
USER app

# Health endpoints only.
EXPOSE 8000
CMD ["collabhub-worker"]
