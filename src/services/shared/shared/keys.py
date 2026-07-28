"""Where a service gets the public key that verifies a token (Conventions §5.1).

Verification is local and stateless: services fetch the Auth service's JWKS,
cache it, and check signatures themselves. Nothing here calls Auth per request —
that would put Auth on the critical path of every request on the platform,
which is exactly what stateless verification exists to avoid.

Two implementations of the same protocol:

* `JwksClient` — what every service except Auth uses. Caches by `kid`, re-fetches
  when a token arrives with a `kid` it has not seen (that is what key rotation
  looks like from the outside), and hard-refreshes hourly.
* `StaticKeySource` — what Auth uses. It holds the signing key already, so
  fetching its own JWKS over HTTP would be a pointless round trip through its
  own ingress.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol, runtime_checkable

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

DEFAULT_HARD_REFRESH_SECONDS = 3600.0
DEFAULT_MIN_REFRESH_SECONDS = 60.0


class UnknownKeyError(LookupError):
    """No verification key matches the token's `kid`."""


@runtime_checkable
class KeySource(Protocol):
    """Resolves a token's `kid` to a key PyJWT can verify with."""

    async def key_for(self, kid: str | None) -> Any: ...


def jwks_document(public_keys: dict[str, RSAPublicKey]) -> dict[str, list[dict[str, str]]]:
    """Build the JWKS body Auth publishes, given `kid` → public key.

    Uses PyJWT's algorithm export so the JSON matches what its own client
    parses; hand-rolling the base64url of `n` and `e` is a well-known way to
    produce a document that almost works.
    """
    algorithm = jwt.get_algorithm_by_name("RS256")
    keys = [
        {**algorithm.to_jwk(public_key, as_dict=True), "kid": kid, "alg": "RS256", "use": "sig"}
        for kid, public_key in public_keys.items()
    ]
    return {"keys": keys}


class StaticKeySource:
    """A fixed set of public keys, held in memory. Used by the Auth service."""

    def __init__(self, public_keys: dict[str, RSAPublicKey]) -> None:
        self._keys = dict(public_keys)

    def replace(self, public_keys: dict[str, RSAPublicKey]) -> None:
        self._keys = dict(public_keys)

    async def key_for(self, kid: str | None) -> RSAPublicKey:
        if kid is None and len(self._keys) == 1:
            return next(iter(self._keys.values()))
        try:
            return self._keys[kid]  # type: ignore[index]
        except KeyError:
            raise UnknownKeyError(f"no key with kid {kid!r}") from None


class JwksClient:
    """Fetches and caches a remote JWKS."""

    def __init__(
        self,
        url: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        hard_refresh_seconds: float = DEFAULT_HARD_REFRESH_SECONDS,
        min_refresh_seconds: float = DEFAULT_MIN_REFRESH_SECONDS,
    ) -> None:
        self._url = url
        self._http = http_client or httpx.AsyncClient(timeout=5.0)
        self._hard_refresh_seconds = hard_refresh_seconds
        self._min_refresh_seconds = min_refresh_seconds
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._miss_refreshed_at = 0.0
        self._lock = asyncio.Lock()

    async def key_for(self, kid: str | None) -> Any:
        if self._is_stale():
            await self._refresh(reason="scheduled")
        if kid not in self._keys:
            await self._refresh(reason="kid-miss")

        try:
            return self._keys[kid]  # type: ignore[index]
        except KeyError:
            raise UnknownKeyError(f"no key with kid {kid!r} at {self._url}") from None

    def _is_stale(self) -> bool:
        return time.monotonic() - self._fetched_at >= self._hard_refresh_seconds

    async def _refresh(self, *, reason: str) -> None:
        async with self._lock:
            if reason == "kid-miss":
                # A kid we have never seen is what key rotation looks like from
                # here, so refetch — but at most once per window, or a stream of
                # tokens bearing a kid that will never exist becomes a stream of
                # requests to Auth. The floor is tracked separately from the
                # scheduled fetch so a rotation moments after startup is still
                # picked up immediately.
                since_miss = time.monotonic() - self._miss_refreshed_at
                if self._miss_refreshed_at and since_miss < self._min_refresh_seconds:
                    return
                self._miss_refreshed_at = time.monotonic()

            response = await self._http.get(self._url)
            response.raise_for_status()
            key_set = jwt.PyJWKSet.from_dict(response.json())
            self._keys = {key.key_id: key.key for key in key_set.keys if key.key_id}
            self._fetched_at = time.monotonic()

    async def aclose(self) -> None:
        await self._http.aclose()
