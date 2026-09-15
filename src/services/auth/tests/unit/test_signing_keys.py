"""The Auth service's RS256 signing material (spec §2, §6).

Auth is the only issuer on the platform, so what it publishes at
`/.well-known/jwks.json` is what every other service trusts. The rules under
test: the private key never leaves the process, retired keys stay verifiable
while tokens signed with them are still alive, and a deployment without a key
fails at startup rather than inventing one.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth.keys import MissingSigningKeyError, SigningKeys


def pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def public_pem(key: rsa.RSAPrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


@pytest.fixture(scope="module")
def a_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def another_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_loads_a_configured_private_key(a_key: rsa.RSAPrivateKey) -> None:
    keys = SigningKeys.load(signing_key_pem=pem(a_key), app_env="production")

    assert keys.private_key.private_numbers() == a_key.private_numbers()


def test_the_key_id_is_derived_from_the_key_itself(a_key: rsa.RSAPrivateKey) -> None:
    """RFC 7638 thumbprint: the same key gets the same `kid` in every replica."""
    first = SigningKeys.load(signing_key_pem=pem(a_key), app_env="production")
    second = SigningKeys.load(signing_key_pem=pem(a_key), app_env="production")

    assert first.active_kid == second.active_kid
    assert first.active_kid


def test_different_keys_get_different_ids(
    a_key: rsa.RSAPrivateKey, another_key: rsa.RSAPrivateKey
) -> None:
    first = SigningKeys.load(signing_key_pem=pem(a_key), app_env="production")
    second = SigningKeys.load(signing_key_pem=pem(another_key), app_env="production")

    assert first.active_kid != second.active_kid


def test_a_missing_key_outside_local_is_a_startup_failure() -> None:
    with pytest.raises(MissingSigningKeyError):
        SigningKeys.load(signing_key_pem="", app_env="production")


def test_a_missing_key_locally_generates_one() -> None:
    """Local runs should need no openssl step; tokens simply die with the process."""
    keys = SigningKeys.load(signing_key_pem="", app_env="local")

    assert keys.active_kid
    assert keys.jwks()["keys"]


def test_the_published_document_carries_no_private_material(a_key: rsa.RSAPrivateKey) -> None:
    keys = SigningKeys.load(signing_key_pem=pem(a_key), app_env="production")

    document = keys.jwks()

    assert [key["kid"] for key in document["keys"]] == [keys.active_kid]
    assert not {"d", "p", "q"} & set(document["keys"][0])


def test_retired_keys_stay_verifiable(
    a_key: rsa.RSAPrivateKey, another_key: rsa.RSAPrivateKey
) -> None:
    """During rotation, tokens signed by the previous key are still in flight."""
    keys = SigningKeys.load(
        signing_key_pem=pem(a_key),
        previous_keys_pem=public_pem(another_key),
        app_env="production",
    )

    published = {key["kid"] for key in keys.jwks()["keys"]}

    assert len(published) == 2
    assert keys.active_kid in published
    assert set(keys.public_keys()) == published


def test_several_retired_keys_can_be_configured_at_once(
    a_key: rsa.RSAPrivateKey, another_key: rsa.RSAPrivateKey
) -> None:
    third = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    keys = SigningKeys.load(
        signing_key_pem=pem(a_key),
        previous_keys_pem=f"{public_pem(another_key)}\n{public_pem(third)}",
        app_env="production",
    )

    assert len(keys.jwks()["keys"]) == 3
