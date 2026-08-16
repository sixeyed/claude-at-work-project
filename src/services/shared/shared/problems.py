"""RFC 7807 Problem Details, implemented once for every service (Conventions §4.2).

Services raise `ProblemException`; these handlers turn it — and anything else
that escapes a route — into `application/problem+json`. A service that writes
its own error body is a service whose clients need a second parser, so the only
route to a non-2xx body is through here.

Two rules are load-bearing rather than cosmetic:

* **`detail` never carries an internal message on a 5xx.** The handler for
  unhandled exceptions drops the exception entirely and logs it instead —
  connection strings and stack frames have ended up in support tickets before.
* **`traceId` is on every problem.** It is the W3C trace id from the incoming
  `traceparent` when there is one, so the error a user pastes into a ticket
  leads directly to the trace and the log lines.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Self

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_BASE_URI = "https://collabhub.dev/problems"

_log = logging.getLogger("collabhub.problems")

# The standard classes from Conventions §4.2. `service-unavailable` is not in
# that list but is needed by the fail-closed half of the denylist rule (§5.2),
# where a request must be refused because it *cannot* be checked.
TITLES: dict[int, tuple[str, str]] = {
    400: ("validation-error", "One or more validation errors occurred."),
    401: ("unauthorized", "Authentication is required."),
    403: ("forbidden", "You do not have access to this resource."),
    404: ("not-found", "The requested resource was not found."),
    409: ("conflict", "The request conflicts with the current state of the resource."),
    429: ("rate-limited", "Too many requests."),
    500: ("internal", "An unexpected error occurred."),
    503: ("service-unavailable", "The service is temporarily unable to handle the request."),
}

_FALLBACK = ("internal", "An unexpected error occurred.")


class ProblemException(Exception):  # noqa: N818 — it *is* a problem, not an "Error"
    """A failure that should reach the client as a Problem Details document."""

    def __init__(
        self,
        status: int,
        *,
        code: str | None = None,
        title: str | None = None,
        detail: str | None = None,
        errors: dict[str, list[str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        default_code, default_title = TITLES.get(status, _FALLBACK)
        self.status = status
        self.code = code or default_code
        self.title = title or default_title
        self.detail = detail
        self.errors = errors
        self.headers = headers
        super().__init__(detail or self.title)

    @classmethod
    def _of(cls, status: int, detail: str | None = None, **kwargs: Any) -> Self:
        return cls(status, detail=detail, **kwargs)

    @classmethod
    def unauthorized(cls, detail: str | None = None, **kwargs: Any) -> Self:
        return cls._of(401, detail, **kwargs)

    @classmethod
    def forbidden(cls, detail: str | None = None, **kwargs: Any) -> Self:
        return cls._of(403, detail, **kwargs)

    @classmethod
    def not_found(cls, detail: str | None = None, **kwargs: Any) -> Self:
        return cls._of(404, detail, **kwargs)

    @classmethod
    def conflict(cls, detail: str | None = None, **kwargs: Any) -> Self:
        return cls._of(409, detail, **kwargs)

    @classmethod
    def rate_limited(cls, detail: str | None = None, **kwargs: Any) -> Self:
        return cls._of(429, detail, **kwargs)

    @classmethod
    def service_unavailable(cls, detail: str | None = None, **kwargs: Any) -> Self:
        return cls._of(503, detail, **kwargs)

    @classmethod
    def validation_error(
        cls, detail: str | None = None, *, errors: dict[str, list[str]] | None = None, **kwargs: Any
    ) -> Self:
        return cls._of(400, detail, errors=errors, **kwargs)


def trace_id(request: Request) -> str:
    """The W3C trace id for this request, or the best available substitute.

    Prefers the trace id out of `traceparent` so the value matches what Tempo
    holds; falls back to `X-Correlation-Id` (Conventions §9) and finally to a
    generated id, because a problem document without a trace id is one nobody
    can follow up.
    """
    traceparent = request.headers.get("traceparent", "")
    parts = traceparent.split("-")
    if len(parts) >= 3 and len(parts[1]) == 32:
        return parts[1]

    return request.headers.get("X-Correlation-Id") or uuid.uuid4().hex


def problem_body(
    problem: ProblemException,
    *,
    instance: str | None = None,
    trace: str | None = None,
) -> dict[str, Any]:
    """The Problem Details document itself, with no `Request` in sight.

    Extracted so a Socket.IO ack and a REST 404 cannot describe the same refusal
    differently. A socket handler has no request to take a path or a trace id
    from, and it still has to tell the client what went wrong in the vocabulary
    the client already parses.

    **`instance` and `traceId` are omitted rather than invented** when the caller
    has none. Conventions §4.2 describes `traceId` as the W3C trace id, and a
    generated one that correlates with nothing in Tempo is worse than its
    absence: it looks like a lead and is not.
    """
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE_URI}/{problem.code}",
        "title": problem.title,
        "status": problem.status,
    }
    if problem.detail is not None:
        body["detail"] = problem.detail
    if instance is not None:
        body["instance"] = instance
    if trace is not None:
        body["traceId"] = trace
    if problem.errors is not None:
        body["errors"] = problem.errors

    return body


def problem_response(request: Request, problem: ProblemException) -> JSONResponse:
    return JSONResponse(
        problem_body(problem, instance=request.url.path, trace=trace_id(request)),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=problem.headers,
    )


def _field_name(location: tuple[Any, ...]) -> str:
    """Pydantic reports ('body', 'name'); clients care about 'name'."""
    parts = [str(part) for part in location if part not in ("body", "query", "path", "header")]
    return ".".join(parts) or "body"


def install_problem_handlers(app: FastAPI) -> None:
    """Register the handlers that give this app a single error envelope."""

    @app.exception_handler(ProblemException)
    async def _domain(request: Request, exc: ProblemException) -> JSONResponse:
        return problem_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: dict[str, list[str]] = {}
        for error in exc.errors():
            errors.setdefault(_field_name(error["loc"]), []).append(error["msg"])
        return problem_response(request, ProblemException.validation_error(errors=errors))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # `detail` on an HTTPException raised inside the framework is a generic
        # phrase like "Not Found"; suppress it rather than repeat the title.
        detail = exc.detail if exc.detail and exc.detail != TITLES.get(exc.status_code) else None
        headers = dict(exc.headers) if exc.headers else None
        return problem_response(
            request,
            ProblemException(exc.status_code, detail=detail, headers=headers),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The message stays in the logs, where it is correlated by trace id, and
        # goes nowhere near the response body.
        _log.exception("unhandled exception", extra={"traceId": trace_id(request)})
        return problem_response(request, ProblemException(500))
