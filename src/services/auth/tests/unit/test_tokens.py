"""Minting access, refresh and service tokens (spec §3.1, Conventions §5.1, §5.5).

These are the claims every other service reads, so the tests assert the wire
format rather than the implementation: claim names, audiences, lifetimes, and
the fact that a refresh token is opaque and stored only as a hash.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from auth.keys import SigningKeys
from auth.tokens import TokenIssuer, hash_refresh_token, new_refresh_token

ISSUER = "https://auth.test"
USER_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


@pytest.fixture(scope="module")
def signing_keys() -> SigningKeys:
    return SigningKeys(rsa.generate_private_key(public_exponent=65537, key_size=2048))


@pytest.fixture
def issuer(signing_keys: SigningKeys) -> TokenIssuer:
    return TokenIssuer(
        keys=signing_keys,
        issuer=ISSUER,
        audience="collabhub",
        internal_audience="collabhub-internal",
        access_token_minutes=15,
        service_token_minutes=10,
    )


def claims_of(token: str, keys: SigningKeys, audience: str = "collabhub") -> dict:
    return jwt.decode(
        token,
        keys.public_keys()[keys.active_kid],
        algorithms=["RS256"],
        issuer=ISSUER,
        audience=audience,
    )


def test_an_access_token_carries_the_claims_every_service_reads(issuer, signing_keys) -> None:
    token = issuer.access_token(
        user_id=USER_ID,
        display_name="Ada Lovelace",
        email="ada@example.com",
        workspace_id=WORKSPACE_ID,
        roles=["owner"],
    )

    claims = claims_of(token.value, signing_keys)

    assert claims["sub"] == str(USER_ID)
    assert claims["name"] == "Ada Lovelace"
    assert claims["email"] == "ada@example.com"
    assert claims["wsp"] == str(WORKSPACE_ID)
    assert claims["roles"] == ["owner"]
    assert claims["iss"] == ISSUER
    assert claims["aud"] == "collabhub"
    assert claims["jti"] == token.token_id


def test_an_access_token_names_the_key_that_signed_it(issuer, signing_keys) -> None:
    """Without `kid`, a verifier cannot follow a rotation."""
    token = issuer.access_token(
        user_id=USER_ID, display_name="Ada", email="a@b.c", workspace_id=WORKSPACE_ID, roles=[]
    )

    assert jwt.get_unverified_header(token.value)["kid"] == signing_keys.active_kid
    assert jwt.get_unverified_header(token.value)["alg"] == "RS256"


def test_an_access_token_expires_when_configured(issuer, signing_keys) -> None:
    token = issuer.access_token(
        user_id=USER_ID, display_name="Ada", email="a@b.c", workspace_id=WORKSPACE_ID, roles=[]
    )

    claims = claims_of(token.value, signing_keys)
    lifetime = claims["exp"] - claims["iat"]

    assert lifetime == 15 * 60
    assert token.expires_in == 15 * 60


def test_every_access_token_has_its_own_id(issuer) -> None:
    """`jti` is what the denylist revokes, so two tokens must never share one."""
    first = issuer.access_token(
        user_id=USER_ID, display_name="Ada", email="a@b.c", workspace_id=WORKSPACE_ID, roles=[]
    )
    second = issuer.access_token(
        user_id=USER_ID, display_name="Ada", email="a@b.c", workspace_id=WORKSPACE_ID, roles=[]
    )

    assert first.token_id != second.token_id


def test_a_service_token_uses_the_internal_audience(issuer, signing_keys) -> None:
    """The audience is the boundary: this token can never satisfy a user route."""
    token = issuer.service_token(client_id="worker", scopes=["assets:write-variants"])

    claims = claims_of(token.value, signing_keys, audience="collabhub-internal")

    assert claims["aud"] == "collabhub-internal"
    assert claims["sub"] == "service:worker"
    assert claims["scp"] == ["assets:write-variants"]
    assert "wsp" not in claims
    assert "roles" not in claims


def test_a_service_token_is_short_lived(issuer, signing_keys) -> None:
    """Revocation is secret rotation, which only works if lifetimes are minutes."""
    token = issuer.service_token(client_id="worker", scopes=[])

    claims = claims_of(token.value, signing_keys, audience="collabhub-internal")

    assert claims["exp"] - claims["iat"] == 10 * 60


def test_a_user_token_is_rejected_when_verified_as_an_internal_one(issuer, signing_keys) -> None:
    token = issuer.access_token(
        user_id=USER_ID, display_name="Ada", email="a@b.c", workspace_id=WORKSPACE_ID, roles=[]
    )

    with pytest.raises(jwt.InvalidAudienceError):
        claims_of(token.value, signing_keys, audience="collabhub-internal")


def test_a_refresh_token_is_opaque_and_unguessable() -> None:
    first, second = new_refresh_token(), new_refresh_token()

    assert first != second
    assert len(first) >= 43  # 256 bits, base64url
    assert "." not in first  # not a JWT: it carries no readable claims


def test_refresh_tokens_are_stored_only_as_hashes() -> None:
    """A leaked database dump must not hand over live sessions."""
    token = new_refresh_token()

    digest = hash_refresh_token(token)

    assert digest == hash_refresh_token(token)
    assert digest != hash_refresh_token(new_refresh_token())
    assert token.encode() not in digest
    assert len(digest) == 32


def test_expiry_is_reported_in_utc(issuer) -> None:
    token = issuer.access_token(
        user_id=USER_ID, display_name="Ada", email="a@b.c", workspace_id=WORKSPACE_ID, roles=[]
    )

    assert token.expires_at.tzinfo is UTC
    assert token.expires_at > datetime.now(UTC) + timedelta(minutes=14)
