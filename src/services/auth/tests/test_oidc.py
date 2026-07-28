"""The relying-party plumbing, without a provider (spec §5.1).

The integration tests run against a real Dex reached at one URL, which is the
normal case and hides the thing most likely to be got wrong: a provider whose
public identity and reachable address differ. That is what these cover, along
with the id_token checks that a cooperative provider will never trigger.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from auth import pkce
from auth.oidc import IdentityRejectedError, OidcClient, ProviderError
from auth.settings import OidcProvider

PUBLIC = "https://auth.example.com/dex"
INTERNAL = "http://dex.svc.cluster.local:5556/dex"
CLIENT_ID = "collabhub-auth"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = "test-key"


def provider(**overrides: Any) -> OidcProvider:
    values: dict[str, Any] = {
        "name": "dex",
        "authority": PUBLIC,
        "internal_authority": INTERNAL,
        "client_id": CLIENT_ID,
        "client_secret": "s3cret",
    }
    values.update(overrides)
    return OidcProvider(**values)


def discovery(issuer: str = PUBLIC) -> dict[str, str]:
    """What a provider advertises: endpoints derived from its own issuer."""
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{PUBLIC}/auth",
        "token_endpoint": f"{PUBLIC}/token",
        "jwks_uri": f"{PUBLIC}/keys",
    }


def jwks() -> dict[str, list[dict[str, str]]]:
    algorithm = jwt.get_algorithm_by_name("RS256")
    exported = algorithm.to_jwk(_KEY.public_key(), as_dict=True)
    return {"keys": [{**exported, "kid": _KID, "alg": "RS256", "use": "sig"}]}


def id_token(**overrides: Any) -> str:
    claims: dict[str, Any] = {
        "iss": PUBLIC,
        "aud": CLIENT_ID,
        "sub": "CgVhZGFtEgVsb2NhbA",
        "email": "ada@collabhub.dev",
        "email_verified": True,
        "name": "ada",
        "nonce": "the-nonce",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": _KID})


def transport(
    *,
    document: dict[str, Any] | None = None,
    token_response: dict[str, Any] | None = None,
    token_status: int = 200,
) -> tuple[httpx.MockTransport, list[str]]:
    """A stand-in provider that records every URL it is asked for.

    The recorded URLs are the assertion for the authority split: they show which
    host each call actually went to.
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=document if document is not None else discovery())
        if path.endswith("/keys"):
            return httpx.Response(200, json=jwks())
        if path.endswith("/token"):
            return httpx.Response(
                token_status,
                json=token_response if token_response is not None else {"id_token": id_token()},
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


def build(**kwargs: Any) -> tuple[OidcClient, list[str]]:
    mock, seen = transport(**kwargs)
    return OidcClient(provider(), http=httpx.AsyncClient(transport=mock)), seen


# --------------------------------------------------------------------------
# The public / internal authority split
# --------------------------------------------------------------------------


async def test_discovery_goes_to_the_internal_authority() -> None:
    client, seen = build()

    await client.metadata()

    assert seen == [f"{INTERNAL}/.well-known/openid-configuration"]


async def test_the_browser_is_sent_to_the_public_authority() -> None:
    """The authorization endpoint is the one URL that must stay public.

    It is where the *user's browser* goes, and a browser cannot resolve an
    in-cluster service name.
    """
    client, _ = build()

    url = await client.authorization_url(
        redirect_uri="http://localhost:8001/api/v1/auth/callback/dex",
        state="s",
        nonce="n",
        code_challenge="c",
    )

    assert url.startswith(f"{PUBLIC}/auth?")


async def test_the_token_exchange_goes_to_the_internal_authority() -> None:
    """Discovery advertised a public token endpoint; we must not call it.

    The provider builds its endpoint list from its issuer, so everything it
    returns points at the public host. Using those verbatim is the bug this
    rewriting exists to prevent: it works on a laptop where both names resolve
    and fails in a cluster where only one does.
    """
    client, seen = build()

    await client.exchange(
        code="c", code_verifier="v", redirect_uri="http://localhost:8001/cb", nonce="the-nonce"
    )

    assert f"{INTERNAL}/token" in seen
    assert f"{PUBLIC}/token" not in seen


async def test_jwks_is_fetched_over_the_internal_authority() -> None:
    client, seen = build()

    await client.exchange(
        code="c", code_verifier="v", redirect_uri="http://localhost:8001/cb", nonce="the-nonce"
    )

    assert f"{INTERNAL}/keys" in seen
    assert f"{PUBLIC}/keys" not in seen


async def test_an_endpoint_outside_the_configured_prefix_is_left_alone() -> None:
    """Only the configured public prefix is swapped, not the host generally.

    A provider that legitimately hosts its keys elsewhere keeps working, and one
    that returns something unexpected fails loudly rather than being silently
    redirected to an address it never named.
    """
    document = discovery() | {"jwks_uri": "https://keys.elsewhere.example/jwks"}
    client, _ = build(document=document)

    metadata = await client.metadata()

    assert metadata.jwks_uri == "https://keys.elsewhere.example/jwks"


async def test_a_provider_falls_back_to_one_authority() -> None:
    """`internalAuthority` is optional — most deployments have a single URL."""
    single = provider(internal_authority="")

    assert single.back_channel == PUBLIC.rstrip("/")
    assert single.front_channel == PUBLIC.rstrip("/")


# --------------------------------------------------------------------------
# Refusing a provider that does not match its configuration
# --------------------------------------------------------------------------


async def test_a_mismatched_issuer_is_refused() -> None:
    """Pointing at the wrong provider looks exactly like this."""
    client, _ = build(document=discovery(issuer="https://someone.else.example"))

    with pytest.raises(ProviderError, match="advertises issuer"):
        await client.metadata()


async def test_a_discovery_document_missing_an_endpoint_is_refused() -> None:
    document = discovery()
    del document["token_endpoint"]
    client, _ = build(document=document)

    with pytest.raises(ProviderError, match="missing"):
        await client.metadata()


async def test_an_unreachable_provider_is_a_provider_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client = OidcClient(provider(), http=httpx.AsyncClient(transport=httpx.MockTransport(refuse)))

    with pytest.raises(ProviderError):
        await client.metadata()


# --------------------------------------------------------------------------
# Refusing an id_token
# --------------------------------------------------------------------------


async def exchange_with(token: str, *, nonce: str = "the-nonce") -> Any:
    client, _ = build(token_response={"id_token": token})
    return await client.exchange(
        code="c", code_verifier="v", redirect_uri="http://localhost:8001/cb", nonce=nonce
    )


async def test_a_good_id_token_becomes_an_identity() -> None:
    identity = await exchange_with(id_token())

    assert identity.subject == "CgVhZGFtEgVsb2NhbA"
    assert identity.email == "ada@collabhub.dev"
    assert identity.email_verified is True
    assert identity.display_name == "ada"
    assert identity.provider_key == "oidc:dex"


async def test_a_wrong_nonce_is_refused() -> None:
    """An id_token obtained elsewhere and injected into someone's callback.

    It is validly signed by the real provider, so every other check passes. The
    nonce is what ties it to *this* login.
    """
    with pytest.raises(IdentityRejectedError, match="nonce"):
        await exchange_with(id_token(nonce="a-different-login"))


async def test_a_token_for_another_audience_is_refused() -> None:
    with pytest.raises(IdentityRejectedError):
        await exchange_with(id_token(aud="some-other-client"))


async def test_a_token_from_another_issuer_is_refused() -> None:
    with pytest.raises(IdentityRejectedError):
        await exchange_with(id_token(iss="https://someone.else.example"))


async def test_an_expired_token_is_refused() -> None:
    with pytest.raises(IdentityRejectedError):
        await exchange_with(id_token(exp=int(time.time()) - 60))


async def test_a_token_signed_by_the_wrong_key_is_refused() -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {
            "iss": PUBLIC,
            "aud": CLIENT_ID,
            "sub": "x",
            "email": "ada@collabhub.dev",
            "nonce": "the-nonce",
            "exp": int(time.time()) + 300,
        },
        other,
        algorithm="RS256",
        headers={"kid": _KID},
    )

    with pytest.raises(IdentityRejectedError):
        await exchange_with(forged)


async def test_an_unsigned_token_is_refused() -> None:
    """`alg: none` — the oldest JWT attack there is."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "kid": _KID}).encode())
    payload = base64.urlsafe_b64encode(
        json.dumps({"iss": PUBLIC, "aud": CLIENT_ID, "sub": "x", "nonce": "the-nonce"}).encode()
    )
    forged = f"{header.rstrip(b'=').decode()}.{payload.rstrip(b'=').decode()}."

    with pytest.raises(IdentityRejectedError):
        await exchange_with(forged)


async def test_a_token_without_an_email_is_refused() -> None:
    """No email means no account to create or match."""
    with pytest.raises(IdentityRejectedError, match="subject or no email"):
        await exchange_with(id_token(email=None))


async def test_the_display_name_falls_back_to_the_local_part() -> None:
    identity = await exchange_with(id_token(name=None))

    assert identity.display_name == "ada"


async def test_a_refused_code_is_an_identity_rejection_not_an_outage() -> None:
    """A 4xx from the token endpoint is a bad code, not a broken provider."""
    client, _ = build(token_status=400, token_response={"error": "invalid_grant"})

    with pytest.raises(IdentityRejectedError, match="refused the code"):
        await client.exchange(
            code="spent", code_verifier="v", redirect_uri="http://x/cb", nonce="n"
        )


# --------------------------------------------------------------------------
# PKCE
# --------------------------------------------------------------------------


def test_a_verifier_satisfies_its_own_challenge() -> None:
    verifier = pkce.new_verifier()

    assert pkce.verifies(verifier, pkce.challenge_for(verifier))


def test_a_different_verifier_does_not() -> None:
    assert not pkce.verifies(pkce.new_verifier(), pkce.challenge_for(pkce.new_verifier()))


def test_challenges_are_base64url_without_padding() -> None:
    challenge = pkce.challenge_for(pkce.new_verifier())

    assert "=" not in challenge
    assert "+" not in challenge and "/" not in challenge


def test_verifiers_are_unique() -> None:
    assert len({pkce.new_verifier() for _ in range(100)}) == 100
