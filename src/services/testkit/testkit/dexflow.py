"""Driving a real sign-in through Dex, the way a browser would.

The Auth service under test runs in-process on an ASGI transport, while Dex runs
in a container over real HTTP. A sign-in crosses between them four times, so
something has to play the browser: follow the redirects, fill in the login form,
and carry the query string from Dex's callback back into the app.

That is what this module is. It exists so the tests can say `sign_in(client,
"ada@...")` and still be exercising the genuine authorization-code flow —
`state`, `nonce`, both PKCE exchanges, the id_token and its signature — rather
than a shortcut around it.

**The one fragile part of the suite lives here.** `_submit_credentials` parses
Dex's login page to find the form action, so a redesign of that page upstream
breaks these tests. That is a deliberate trade. The alternative is Dex's
`mockCallback` connector, which needs no form at all but authenticates one
hard-coded user — and multiple users are exactly what the workspace switcher,
the members list and the role checks need. When a Dex bump breaks this, the fix
is here, and `docs/platform/versions.md` says so.
"""

from __future__ import annotations

import re
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from auth import cookies, pkce

# Dex's login form: `<form method="post" action="/dex/auth/local/login?...">`
_FORM_ACTION = re.compile(r'<form[^>]+action="([^"]+)"', re.IGNORECASE)

_REDIRECTS = (httpx.codes.FOUND, httpx.codes.SEE_OTHER, httpx.codes.TEMPORARY_REDIRECT)


async def _follow_within(browser: httpx.AsyncClient, response: httpx.Response, host: str):
    """Follow redirects for as long as they stay on `host`.

    Stops at the first redirect that leaves it — which is the callback into the
    Auth service, the thing the caller actually wants.
    """
    while response.status_code in _REDIRECTS:
        target = response.url.join(response.headers["location"])
        if target.host != host or target.port != response.url.port:
            return response
        response = await browser.get(target)
    return response


async def _submit_credentials(
    browser: httpx.AsyncClient, page: httpx.Response, email: str, password: str
) -> httpx.Response:
    match = _FORM_ACTION.search(page.text)
    if match is None:
        raise AssertionError(
            "Dex's login page has no form — its markup has probably changed.\n"
            f"Status {page.status_code} at {page.url}:\n{page.text[:500]}"
        )

    action = page.url.join(match.group(1).replace("&amp;", "&"))
    return await browser.post(action, data={"login": email, "password": password})


async def authenticate(authorize_url: str, *, email: str, password: str) -> dict[str, list[str]]:
    """Sign in at Dex and return the query parameters of its callback redirect.

    Takes the URL the Auth service redirected the browser to, and gives back
    what Dex hands to `/auth/callback/{provider}` — the `code` and `state`, or
    an `error`.
    """
    origin = urlparse(authorize_url)

    async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as browser:
        page = await _follow_within(browser, await browser.get(authorize_url), origin.hostname)
        submitted = await _submit_credentials(browser, page, email, password)
        final = await _follow_within(browser, submitted, origin.hostname)

    if final.status_code not in _REDIRECTS:
        raise AssertionError(
            f"expected Dex to redirect back after login, got {final.status_code}:\n"
            f"{final.text[:500]}"
        )

    return parse_qs(urlparse(str(final.url.join(final.headers["location"]))).query)


async def sign_in(
    client: httpx.AsyncClient,
    *,
    email: str,
    password: str,
    provider: str = "dex",
) -> dict[str, Any]:
    """A complete sign-in: login → Dex → callback → token exchange.

    Returns the token pair, so tests that only need a signed-in user can ignore
    everything in between.
    """
    result = await begin(client, email=email, password=password, provider=provider)
    return await finish(client, result)


class Attempt(dict):
    """One in-flight sign-in, so a test can interfere partway through."""


async def begin(
    client: httpx.AsyncClient,
    *,
    email: str,
    password: str,
    provider: str = "dex",
    code_challenge: str | None = None,
) -> Attempt:
    """Run a sign-in as far as the SPA holding an authorization code."""
    verifier = pkce.new_verifier()
    challenge = code_challenge or pkce.challenge_for(verifier)

    started = await client.get(
        f"/api/v1/auth/login/{provider}", params={"codeChallenge": challenge}
    )
    assert started.status_code == httpx.codes.FOUND, started.text

    callback_params = await authenticate(
        started.headers["location"], email=email, password=password
    )
    query = {key: values[0] for key, values in callback_params.items()}

    returned = await client.get(f"/api/v1/auth/callback/{provider}", params=query)
    assert returned.status_code == httpx.codes.FOUND, returned.text

    spa = parse_qs(urlparse(returned.headers["location"]).query)

    return Attempt(
        verifier=verifier,
        challenge=challenge,
        callback=query,
        spa=spa,
        code=spa.get("code", [None])[0],
        error=spa.get("error", [None])[0],
    )


async def finish(
    client: httpx.AsyncClient, attempt: Attempt, *, verifier: str | None = None
) -> dict[str, Any]:
    """Exchange the authorization code for a session.

    Returns the response body plus `refreshCookie` — the value of the `HttpOnly`
    cookie the server set. A real browser would never expose that, and neither
    does the SPA; the tests read it off the response so they can hold **several
    sessions at once**. Signing in twice on one client would otherwise overwrite
    the cookie jar, and every multi-user test would silently be asserting about
    whichever user signed in last.

    Pass it back with `session_cookie(...)` to say explicitly whose session a
    request belongs to.
    """
    assert attempt["code"], f"sign-in did not produce a code: {attempt['spa']}"

    resp = await client.post(
        "/api/v1/auth/token",
        json={
            "grantType": "authorization_code",
            "code": attempt["code"],
            "codeVerifier": verifier or attempt["verifier"],
        },
    )
    assert resp.status_code == httpx.codes.OK, resp.text

    issued = issued_cookie(resp)
    assert issued, f"no {cookies.COOKIE_NAME} cookie on the token response"

    # Drop it from the jar so it cannot be sent implicitly by a later request —
    # every test that needs it names the session it means.
    client.cookies.delete(cookies.COOKIE_NAME, path=cookies.COOKIE_PATH)

    return {**resp.json(), "refreshCookie": issued}


def issued_cookie(response: httpx.Response) -> str | None:
    """The refresh cookie's value, read from the raw `Set-Cookie` header.

    Not from httpx's cookie jar: the jar behaves like a browser and discards a
    cookie whose `Max-Age` is zero, which is exactly what the service sends when
    `AUTH_REFRESH_TOKEN_DAYS=0`. Correct of the jar, useless to a test that wants
    to present the token it was just handed.
    """
    for header in response.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(header)
        if cookies.COOKIE_NAME in jar:
            return jar[cookies.COOKIE_NAME].value
    return None


def session_cookie(tokens: dict[str, Any]) -> dict[str, str]:
    """Headers naming one session's refresh cookie.

    An explicit `Cookie` header rather than httpx's `cookies=` argument: that one
    is deprecated precisely because whose cookie jar wins is ambiguous, which is
    the ambiguity these tests exist to avoid.

    Merge with a bearer header when a request needs both:
    `headers={**bearer(tokens), **session_cookie(tokens)}`.
    """
    return {"Cookie": f"{cookies.COOKIE_NAME}={tokens['refreshCookie']}"}


def renewed(response: httpx.Response) -> dict[str, Any]:
    """Read a rotated session off a `/refresh` or `/switch-workspace` response.

    Rotation issues a new cookie on every renewal, so a test that renews and then
    keeps using the *original* session dict is testing a token the server has
    already retired.
    """
    issued = issued_cookie(response)
    assert issued, f"no rotated {cookies.COOKIE_NAME} cookie on {response.request.url}"
    return {**response.json(), "refreshCookie": issued}
