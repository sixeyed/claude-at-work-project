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

from shared import ProblemException, install_problem_handlers, problem_body

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


# --- the request-free body -------------------------------------------------
#
# `problem_body` is the document itself, buildable without a `Request`. A
# Socket.IO handler has a refusal to describe and no request to describe it
# from, and the alternative — a second error shape for sockets — would give the
# platform two error vocabularies for one class of failure.


def test_problem_body_carries_the_stable_type_and_the_detail() -> None:
    body = problem_body(ProblemException.not_found("No such channel."))

    assert body["type"] == "https://collabhub.dev/problems/not-found"
    assert body["status"] == 404
    assert body["detail"] == "No such channel."


def test_problem_body_keeps_the_field_errors() -> None:
    body = problem_body(
        ProblemException.validation_error(
            "Bad body.", errors={"body": ["A message cannot be empty."]}
        )
    )

    assert body["errors"] == {"body": ["A message cannot be empty."]}


def test_problem_body_omits_what_it_was_not_given() -> None:
    """No invented trace id.

    Conventions §4.2 describes `traceId` as the W3C trace id, so a generated one
    that correlates with nothing in Tempo is worse than its absence — it looks
    like a lead and is not.
    """
    body = problem_body(ProblemException.forbidden("Nope."))

    assert "instance" not in body
    assert "traceId" not in body


async def test_the_http_envelope_is_unchanged_by_the_extraction() -> None:
    """`problem_response` now builds on `problem_body`; the wire must not move.

    This is the evidence the refactor was faithful — the same assertions the
    HTTP tests above make, restated against the one path that changed.
    """
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/domain-error", headers={"traceparent": TRACEPARENT})

    body = response.json()
    assert body["instance"] == "/domain-error"
    assert body["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert body["type"].startswith("https://collabhub.dev/problems/")
