#!/usr/bin/env -S uv run --with httpx --no-project --quiet python
"""Sign in through Dex from the command line and print a token pair.

Federated login is a browser flow — three redirects and an HTML form — which is
exactly what makes it awkward to drive from a `.http` file or a curl one-liner.
This script plays the browser so that manual API poking still starts with a real
token obtained the real way, rather than a shortcut that only exists for
convenience and then becomes something people depend on.

    ./scripts/sign-in.py                       # ada, as JSON
    ./scripts/sign-in.py grace@collabhub.dev   # someone else
    ./scripts/sign-in.py --access-token        # just the token, for $(…)
    ./scripts/sign-in.py --refresh-cookie      # the cookie, for api.http

The refresh token comes back as an `HttpOnly` cookie rather than in the response
body (register D22), so this script keeps a cookie jar the way a browser would.
`--refresh-cookie` prints that value, which is the one thing a browser would
never reveal — it exists so `api.http` can send a `Cookie` header by hand.

It only works against a local stack with Dex's static passwords. There is
nothing here that would work against a real identity provider, and that is the
point: this is a development convenience, not a supported grant.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import httpx

DEFAULT_AUTH = os.environ.get("AUTH_URL", "http://localhost:8001")
DEFAULT_EMAIL = "ada@collabhub.dev"
DEFAULT_PASSWORD = os.environ.get("DEX_PASSWORD", "collabhub")

FORM_ACTION = re.compile(r'<form[^>]+action="([^"]+)"', re.IGNORECASE)
REDIRECTS = (301, 302, 303, 307, 308)
REFRESH_COOKIE = "collabhub_rt"


def refresh_cookie(response: httpx.Response) -> str | None:
    """The refresh cookie's value, from the raw header rather than the jar."""
    for header in response.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(header)
        if REFRESH_COOKIE in jar:
            return jar[REFRESH_COOKIE].value
    return None


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def follow_within(client: httpx.Client, response: httpx.Response, host: str) -> httpx.Response:
    """Follow redirects while they stay on `host`; stop at the first that leaves."""
    while response.status_code in REDIRECTS:
        target = response.url.join(response.headers["location"])
        if target.host != host or target.port != response.url.port:
            return response
        response = client.get(target)
    return response


def sign_in(auth_url: str, provider: str, email: str, password: str) -> dict:
    verifier = b64url(os.urandom(32))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())

    with httpx.Client(follow_redirects=False, timeout=15.0) as client:
        started = client.get(
            f"{auth_url}/api/v1/auth/login/{provider}",
            params={"codeChallenge": challenge, "codeChallengeMethod": "S256"},
        )
        if started.status_code != httpx.codes.FOUND:
            raise SystemExit(
                f"/auth/login/{provider} answered {started.status_code}: {started.text}"
            )

        authorize = started.headers["location"]
        idp_host = urlparse(authorize).hostname

        page = follow_within(client, client.get(authorize), idp_host)
        match = FORM_ACTION.search(page.text)
        if match is None:
            raise SystemExit(
                "no login form at the identity provider — its page markup may have changed"
            )

        action = page.url.join(match.group(1).replace("&amp;", "&"))
        submitted = client.post(action, data={"login": email, "password": password})
        final = follow_within(client, submitted, idp_host)

        if final.status_code not in REDIRECTS:
            raise SystemExit(f"sign-in failed — check the email and password:\n{final.text[:400]}")

        callback = final.url.join(final.headers["location"])
        returned = client.get(callback)
        spa = parse_qs(urlparse(returned.headers["location"]).query)
        if "code" not in spa:
            raise SystemExit(f"the callback refused this sign-in: {spa}")

        exchanged = client.post(
            f"{auth_url}/api/v1/auth/token",
            json={
                "grantType": "authorization_code",
                "code": spa["code"][0],
                "codeVerifier": verifier,
            },
        )
        if exchanged.status_code != httpx.codes.OK:
            raise SystemExit(f"/auth/token answered {exchanged.status_code}: {exchanged.text}")

        issued = refresh_cookie(exchanged)
        if not issued:
            raise SystemExit("/auth/token set no refresh cookie")

        return {**exchanged.json(), "refreshCookie": issued}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email", nargs="?", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--provider", default="dex")
    parser.add_argument("--auth-url", default=DEFAULT_AUTH)
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--access-token",
        action="store_true",
        help="print only the access token, for use in a shell substitution",
    )
    output.add_argument(
        "--refresh-cookie",
        action="store_true",
        help=f"print only the {REFRESH_COOKIE} cookie value, for a Cookie header",
    )
    args = parser.parse_args()

    tokens = sign_in(args.auth_url, args.provider, args.email, args.password)

    if args.access_token:
        print(tokens["accessToken"])
    elif args.refresh_cookie:
        print(tokens["refreshCookie"])
    else:
        json.dump(tokens, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
