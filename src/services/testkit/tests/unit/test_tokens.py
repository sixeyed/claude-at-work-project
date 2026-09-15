"""The two kinds of token `testkit.tokens.Tokens` mints (Conventions §5.1, §5.5).

Decoded without verification: what is under test is the claim set, not
PyJWT's signature check, which the services' own integration tests exercise.
"""

from __future__ import annotations

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from testkit.tokens import INTERNAL_AUDIENCE, ISSUER, KEY_ID, USER_AUDIENCE, Tokens


@pytest.fixture(scope="module")
def minter() -> Tokens:
    return Tokens(rsa.generate_private_key(public_exponent=65537, key_size=2048))


def claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def test_a_user_token_carries_exactly_the_conventions_claims(minter):
    decoded = claims(minter.mint())

    assert set(decoded) == {
        "iss",
        "aud",
        "iat",
        "exp",
        "jti",
        "sub",
        "name",
        "email",
        "wsp",
        "roles",
    }
    assert decoded["iss"] == ISSUER
    assert decoded["aud"] == USER_AUDIENCE
    assert decoded["sub"] == str(Tokens.ADA)
    assert decoded["wsp"] == str(Tokens.WORKSPACE)
    assert decoded["roles"] == ["member"]


def test_a_service_token_is_for_the_internal_audience(minter):
    decoded = claims(minter.service("worker", scopes=("assets:write-variants",)))

    assert decoded["aud"] == INTERNAL_AUDIENCE
    assert decoded["sub"] == "service:worker"
    assert decoded["scp"] == ["assets:write-variants"]
    assert "wsp" not in decoded


def test_an_override_of_none_removes_the_claim(minter):
    assert "wsp" not in claims(minter.mint(wsp=None))


def test_every_token_is_unique_and_names_its_key(minter):
    first, second = minter.mint(), minter.mint()

    assert claims(first)["jti"] != claims(second)["jti"]
    assert jwt.get_unverified_header(first)["kid"] == KEY_ID
    assert jwt.get_unverified_header(minter.mint(kid="rotated"))["kid"] == "rotated"
