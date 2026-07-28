"""The JWKS endpoint — how every other service comes to trust these tokens.

Deliberately outside `/api/v1`: `/.well-known/` is where RFC 8615 says clients
look, and the JWKS URL is baked into every service's config.

It is cacheable and must stay that way. Verification happens on every request on
the platform; if each verifier fetched this document per request, stateless auth
would have quietly turned the Auth service into the busiest thing in the cluster
(Conventions §5.3, spec §8).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

JWKS_MAX_AGE_SECONDS = 300

router = APIRouter(tags=["well-known"])


@router.get("/.well-known/jwks.json")
async def jwks(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = f"public, max-age={JWKS_MAX_AGE_SECONDS}"
    return request.app.state.signing_keys.jwks()
