"""Cross-origin access for the SPA, configured once for every service.

Locally the SPA and the services are separate origins — the browser loads the
app from `localhost:5173` and it calls `localhost:8001`, `:8002` and so on — so
without this every request from the app is blocked before it is sent.

Deployed, they are usually one origin behind a single ingress and none of this
is needed. That is why the default is **no origins and no middleware at all**:
an empty `CORS_ALLOWED_ORIGINS` installs nothing, so a service that does not
need cross-origin access does not quietly advertise that it allows it.

Two choices worth stating:

* **Origins are listed, never `*`.** A wildcard is easy and means any page on the
  internet can call these APIs from a victim's browser. The list is short and
  lives in configuration. With credentials allowed, browsers reject a wildcard
  outright anyway — which is the right instinct made mandatory.
* **Credentials are allowed**, because the refresh token is an `HttpOnly` cookie
  (register D22) and a cross-origin `fetch` will not attach it otherwise. Access
  tokens are still a Bearer header (Conventions §5.1); the cookie is only ever
  sent to `/api/v1/auth`, so the other services receive no ambient credential at
  all even though they permit them here.

Allowing credentials is what makes CSRF a question, and it is answered by the
cookie rather than here: `SameSite=Strict` means no cross-site request carries
the refresh cookie, so there is nothing for a forged request to ride on. That
also means the SPA and the API must stay **same-site** — see `auth/cookies.py`,
which owns that constraint.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# Only what the platform actually uses. `traceparent` is on the list because
# browser requests carry it for distributed tracing (Conventions §9), and a
# header the browser sends but the preflight does not allow fails the request.
ALLOWED_HEADERS = ["Authorization", "Content-Type", "traceparent", "X-Correlation-Id"]
ALLOWED_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]


def install_cors(app: FastAPI, *, origins: list[str]) -> None:
    """Allow the configured origins to call this service from a browser.

    A no-op when no origins are configured, which is the deployed case.
    """
    if not origins:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        max_age=600,
    )
