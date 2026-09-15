"""Signing-key sources for token verification (Conventions §5.1).

Every service verifies RS256 tokens locally against the Auth service's JWKS —
there is no per-request call to Auth — so the behaviour that matters here is
caching: fetch once, refresh when an unknown `kid` shows up, and re-fetch
hourly. Auth itself holds the private key and uses `StaticKeySource` instead of
HTTP-calling its own endpoint.
"""

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from shared import JwksClient, StaticKeySource, UnknownKeyError, jwks_document


@pytest.fixture(scope="module")
def key_pair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_key_pair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _JwksServer:
    """A stand-in Auth service that counts how often its JWKS is fetched."""

    def __init__(self, document: dict) -> None:
        self.document = document
        self.fetches = 0
        self.app = Starlette(routes=[Route("/.well-known/jwks.json", self._serve)])

    async def _serve(self, request: httpx.Request) -> JSONResponse:
        self.fetches += 1
        return JSONResponse(self.document)

    def client(self, **kwargs) -> JwksClient:
        transport = httpx.ASGITransport(app=self.app)
        http = httpx.AsyncClient(transport=transport, base_url="http://auth")
        return JwksClient("http://auth/.well-known/jwks.json", http_client=http, **kwargs)


def test_jwks_document_publishes_only_public_material(key_pair: rsa.RSAPrivateKey) -> None:
    document = jwks_document({"key-1": key_pair.public_key()})

    assert len(document["keys"]) == 1
    key = document["keys"][0]
    assert key["kid"] == "key-1"
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    # The private exponent and primes must never appear in a published document.
    assert not {"d", "p", "q", "dp", "dq", "qi"} & set(key)


async def test_static_source_returns_the_key_for_a_known_id(key_pair: rsa.RSAPrivateKey) -> None:
    source = StaticKeySource({"key-1": key_pair.public_key()})

    assert await source.key_for("key-1") is not None


async def test_static_source_rejects_an_unknown_key_id(key_pair: rsa.RSAPrivateKey) -> None:
    source = StaticKeySource({"key-1": key_pair.public_key()})

    with pytest.raises(UnknownKeyError):
        await source.key_for("key-2")


async def test_jwks_client_fetches_once_and_caches(key_pair: rsa.RSAPrivateKey) -> None:
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client()

    await client.key_for("key-1")
    await client.key_for("key-1")

    assert server.fetches == 1


async def test_jwks_client_refetches_when_it_sees_an_unknown_key_id(
    key_pair: rsa.RSAPrivateKey, other_key_pair: rsa.RSAPrivateKey
) -> None:
    """Key rotation: Auth starts signing with a new kid and services follow."""
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client(min_refresh_seconds=0)
    await client.key_for("key-1")

    server.document = jwks_document(
        {"key-1": key_pair.public_key(), "key-2": other_key_pair.public_key()}
    )

    assert await client.key_for("key-2") is not None
    assert server.fetches == 2


async def test_jwks_client_still_rejects_an_id_the_refetch_did_not_produce(
    key_pair: rsa.RSAPrivateKey,
) -> None:
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client(min_refresh_seconds=0)

    with pytest.raises(UnknownKeyError):
        await client.key_for("nonsense")


async def test_jwks_client_does_not_refetch_faster_than_its_floor(
    key_pair: rsa.RSAPrivateKey,
) -> None:
    """A burst of tokens with a bogus kid must not become a burst of fetches."""
    server = _JwksServer(jwks_document({"key-1": key_pair.public_key()}))
    client = server.client(min_refresh_seconds=300)
    await client.key_for("key-1")

    for _ in range(5):
        with pytest.raises(UnknownKeyError):
            await client.key_for("bogus")

    assert server.fetches == 2
