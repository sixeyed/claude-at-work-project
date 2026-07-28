"""Cross-origin access for the SPA.

The case worth a test is the default: no configured origins must install no
middleware, so a service deployed same-origin does not advertise cross-origin
access it was never meant to allow.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from shared import install_cors

ORIGIN = "http://localhost:5173"


def build(origins: list[str]) -> FastAPI:
    app = FastAPI()
    install_cors(app, origins=origins)

    @app.get("/thing")
    async def thing() -> dict[str, bool]:
        return {"ok": True}

    return app


async def call(app: FastAPI, origin: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/thing", headers={"Origin": origin})


async def preflight(app: FastAPI, origin: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.options(
            "/thing",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )


async def test_a_configured_origin_is_allowed() -> None:
    response = await call(build([ORIGIN]), ORIGIN)

    assert response.headers["access-control-allow-origin"] == ORIGIN


async def test_an_unlisted_origin_gets_no_allow_header() -> None:
    """No wildcard: an origin that is not on the list is simply not answered for."""
    response = await call(build([ORIGIN]), "https://evil.example")

    assert "access-control-allow-origin" not in response.headers


async def test_no_configured_origins_installs_nothing() -> None:
    """The deployed default. Same-origin behind an ingress needs no CORS at all."""
    response = await call(build([]), ORIGIN)

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_the_authorization_header_survives_preflight() -> None:
    """Every authenticated call carries it, so a preflight that drops it breaks everything."""
    response = await preflight(build([ORIGIN]), ORIGIN)

    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed


async def test_credentials_are_allowed() -> None:
    """Without this the browser drops the refresh cookie on cross-origin calls.

    CSRF is closed by `SameSite=Strict` on the cookie itself rather than by
    refusing credentials here — see `auth/cookies.py`.
    """
    response = await call(build([ORIGIN]), ORIGIN)

    assert response.headers["access-control-allow-credentials"] == "true"


async def test_credentials_are_never_paired_with_a_wildcard() -> None:
    """A browser rejects `*` outright once credentials are in play."""
    response = await call(build([ORIGIN]), ORIGIN)

    assert response.headers["access-control-allow-origin"] != "*"


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
async def test_the_methods_the_api_uses_are_allowed(method: str) -> None:
    response = await preflight(build([ORIGIN]), ORIGIN)

    assert method in response.headers["access-control-allow-methods"]
