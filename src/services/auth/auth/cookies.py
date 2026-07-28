"""The refresh-token cookie (register D22).

The refresh token is the long-lived half of a session — thirty days against the
access token's fifteen minutes — so it is the one worth stealing. It is
delivered as a cookie the browser's JavaScript cannot read, rather than in a
response body, because a token that never enters the JS heap cannot be taken by
injected script. `sessionStorage` and `localStorage` are both readable by any
code running on the origin, which is exactly the code an XSS gives an attacker.

The attributes are the whole security control, so each is deliberate:

* **`HttpOnly`** — the point. No `document.cookie`, no `fetch` response body,
  nothing for injected script to read. The SPA never sees this value, which is
  why `/auth/refresh` and `/auth/switch-workspace` take no token in their bodies.
* **`SameSite=Strict`** — closes CSRF without a separate anti-forgery token. Once
  the browser attaches a credential automatically, any site can try to trigger
  `POST /auth/refresh`; `Strict` means no cross-site request carries the cookie
  at all, so there is nothing to forge. This is what makes the same-site
  deployment constraint below load-bearing rather than a preference.
* **`Secure`** — HTTPS only. Browsers treat `http://localhost` as a trustworthy
  origin and accept it there, so local development needs no exception.
* **`Path=/api/v1/auth`** — the cookie is only ever sent to the endpoints that
  spend it. Messaging, Canvas and Asset never receive it, so a bug in one of them
  cannot log it.
* **`Max-Age`** — matched to the token's own lifetime, so the browser stops
  sending a cookie the database would refuse anyway.

**Deployments must keep the SPA and the API same-site** — one registrable domain
(`app.collabhub.dev` and `api.collabhub.dev`), or one origin behind a single
ingress. Ports and subdomains do not affect what "site" means, so
`localhost:5173` and `localhost:8001` already qualify. A deployment that split
them across genuinely different domains would silently stop sending the cookie
under `Strict`, and recovering would mean `SameSite=None` plus a double-submit
anti-CSRF token — a different design, not a config change.
"""

from __future__ import annotations

from fastapi import Request, Response

COOKIE_NAME = "collabhub_rt"
COOKIE_PATH = "/api/v1/auth"
SAME_SITE = "strict"

SECONDS_PER_DAY = 86400


def read(request: Request) -> str | None:
    """The refresh token the browser presented, if any."""
    return request.cookies.get(COOKIE_NAME)


def issue(response: Response, token: str, *, refresh_token_days: int, secure: bool = True) -> None:
    """Attach a rotated refresh token to the response."""
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=refresh_token_days * SECONDS_PER_DAY,
        path=COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=SAME_SITE,
    )


def clear(response: Response, *, secure: bool = True) -> None:
    """Remove the cookie on sign-out.

    The attributes have to match the ones it was set with — a browser identifies
    a cookie by name, domain and path, so clearing it with a different path
    leaves the original in place and the user apparently still signed in.
    """
    response.delete_cookie(
        COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite=SAME_SITE,
    )
