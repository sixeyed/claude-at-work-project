"""RFC 7807 Problem Details (Conventions §4.2).

Every non-2xx response on every service goes through these handlers, so the
tests pin the envelope itself: the media type, the stable `type` URI, the
request path in `instance`, and the trace id that makes a log line findable
from an error a user reported.
"""

import httpx
import pytest
from fastapi import FastAPI
from fastapi import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from shared import ProblemException, install_problem_handlers

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class _Body(BaseModel):
    name: str
    count: int


def _app() -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/domain-error")
    async def domain_error() -> None:
        raise ProblemException.not_found("No channel with that id.")

    @app.get("/http-error")
    async def http_error() -> None:
        raise StarletteHTTPException(status_code=403)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("password=hunter2 in the connection string")

    @app.post("/validated")
    async def validated(body: _Body) -> dict[str, str]:
        return {"ok": "yes"}

    return app


@pytest.fixture
def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=_app(), raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_domain_error_returns_a_problem_document(client: httpx.AsyncClient) -> None:
    resp = await client.get("/domain-error")

    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json() == {
        "type": "https://collabhub.dev/problems/not-found",
        "title": "The requested resource was not found.",
        "status": 404,
        "detail": "No channel with that id.",
        "instance": "/domain-error",
        "traceId": resp.json()["traceId"],
    }


async def test_uses_the_incoming_w3c_trace_id(client: httpx.AsyncClient) -> None:
    resp = await client.get("/domain-error", headers={"traceparent": TRACEPARENT})

    assert resp.json()["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736"


async def test_falls_back_to_the_correlation_id_header(client: httpx.AsyncClient) -> None:
    resp = await client.get("/domain-error", headers={"X-Correlation-Id": "abc-123"})

    assert resp.json()["traceId"] == "abc-123"


async def test_generates_a_trace_id_when_the_caller_supplies_none(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/domain-error")

    assert resp.json()["traceId"]


async def test_validation_failures_report_the_offending_fields(client: httpx.AsyncClient) -> None:
    resp = await client.post("/validated", json={"count": "not-a-number"})

    assert resp.status_code == 400
    assert resp.json()["type"] == "https://collabhub.dev/problems/validation-error"
    assert set(resp.json()["errors"]) == {"name", "count"}
    assert resp.json()["errors"]["name"] == ["Field required"]


async def test_plain_http_exceptions_are_mapped_to_the_matching_problem_class(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/http-error")

    assert resp.status_code == 403
    assert resp.json()["type"] == "https://collabhub.dev/problems/forbidden"
    assert resp.headers["content-type"] == "application/problem+json"


async def test_unhandled_exceptions_never_leak_the_internal_message(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/boom")

    assert resp.status_code == 500
    assert resp.json()["type"] == "https://collabhub.dev/problems/internal"
    assert "hunter2" not in resp.text
    assert "detail" not in resp.json()


async def test_problem_exceptions_carry_their_response_headers(
    client: httpx.AsyncClient,
) -> None:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/limited")
    async def limited() -> None:
        raise ProblemException.rate_limited("Slow down.", headers={"Retry-After": "30"})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/limited")

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "30"
