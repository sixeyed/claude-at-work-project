"""RS256 signing material for the only issuer on the platform (spec §2).

One key signs; several may verify. That split is what makes rotation possible:
publish the new key, start signing with it, and keep the old public key in
`AUTH_PREVIOUS_KEYS` until every token it signed has expired.

Key ids are RFC 7638 thumbprints rather than names, so every replica of this
service derives the same `kid` from the same key with nothing to configure and
nothing to keep in sync.

Locally, an unset `AUTH_SIGNING_KEY` generates a throwaway pair so a fresh clone
runs with no openssl step; tokens then die with the process, which is correct
for a laptop and unacceptable anywhere else — hence the hard failure outside
`local`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from shared import jwks_document

LOCAL_ENV = "local"
KEY_SIZE = 2048

_log = logging.getLogger("collabhub.auth.keys")


class MissingSigningKeyError(RuntimeError):
    """No signing key was configured, and this environment will not invent one."""


def key_id(public_key: RSAPublicKey) -> str:
    """The RFC 7638 thumbprint of a key — stable across processes and restarts.

    The spec is exact about the input: the required members only (`e`, `kty`,
    `n` for RSA), lexicographically ordered, no whitespace, SHA-256, base64url
    without padding. Any deviation still produces *an* id, just not one another
    implementation would agree with.
    """
    jwk = jwt.get_algorithm_by_name("RS256").to_jwk(public_key, as_dict=True)
    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]}, separators=(",", ":"), sort_keys=True
    )
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _load_public_keys(pem_bundle: str) -> list[RSAPublicKey]:
    """Parse the concatenated PEM public keys in `AUTH_PREVIOUS_KEYS`."""
    keys: list[RSAPublicKey] = []
    marker = "-----BEGIN PUBLIC KEY-----"
    for block in pem_bundle.split(marker):
        if not block.strip():
            continue
        loaded = serialization.load_pem_public_key(f"{marker}{block}".encode())
        if not isinstance(loaded, RSAPublicKey):
            raise ValueError("AUTH_PREVIOUS_KEYS must contain RSA public keys")
        keys.append(loaded)
    return keys


class SigningKeys:
    """The active signing key plus any retired keys still worth verifying."""

    def __init__(
        self, private_key: RSAPrivateKey, previous: list[RSAPublicKey] | None = None
    ) -> None:
        self.private_key = private_key
        self.active_kid = key_id(private_key.public_key())
        self._public_keys = {self.active_kid: private_key.public_key()}
        for retired in previous or []:
            self._public_keys.setdefault(key_id(retired), retired)

    @classmethod
    def load(
        cls,
        *,
        signing_key_pem: str,
        previous_keys_pem: str = "",
        app_env: str = LOCAL_ENV,
    ) -> SigningKeys:
        if signing_key_pem.strip():
            loaded = serialization.load_pem_private_key(
                signing_key_pem.strip().encode(), password=None
            )
            if not isinstance(loaded, RSAPrivateKey):
                raise ValueError("AUTH_SIGNING_KEY must be an RSA private key")
            return cls(loaded, _load_public_keys(previous_keys_pem))

        if app_env != LOCAL_ENV:
            raise MissingSigningKeyError(
                "AUTH_SIGNING_KEY is required outside local development: "
                "a generated key would invalidate every token on restart and "
                "differ between replicas."
            )

        _log.warning(
            "AUTH_SIGNING_KEY is unset; generating a throwaway key for local use. "
            "Tokens will not survive a restart."
        )
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE))

    def public_keys(self) -> dict[str, RSAPublicKey]:
        return dict(self._public_keys)

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        """The document served at `/.well-known/jwks.json`."""
        return jwks_document(self._public_keys)
