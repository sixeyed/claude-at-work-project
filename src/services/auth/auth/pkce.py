"""PKCE — proving that whoever redeems a code is who asked for it (RFC 7636).

Two independent exchanges in this service use it, for the same reason in
opposite directions:

* **Auth ↔ upstream provider.** This service generates the verifier, keeps it in
  R1, and proves ownership when it redeems the provider's code.
* **SPA ↔ Auth.** The SPA generates the verifier, sends only its challenge on
  `/auth/login/{provider}`, and reveals the verifier at `/auth/token`.

The second is what makes the CollabHub authorization code safe to put in a
redirect URL. That code travels through the browser's address bar and lands in
history; without PKCE, anything that can read it can spend it. With PKCE it is
useless without a secret that never left the SPA's memory.

S256 only. RFC 7636 also allows `plain`, where the "challenge" is the verifier
itself — which proves nothing, and exists for clients that cannot compute a
SHA-256. Ours can.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

VERIFIER_BYTES = 32
METHOD_S256 = "S256"


def _b64url(raw: bytes) -> str:
    """base64url with the padding stripped, as every OAuth spec expects."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def new_verifier() -> str:
    """A fresh code verifier — 256 bits, URL-safe, never leaves the holder."""
    return _b64url(secrets.token_bytes(VERIFIER_BYTES))


def challenge_for(verifier: str) -> str:
    """The S256 challenge derived from a verifier."""
    return _b64url(hashlib.sha256(verifier.encode()).digest())


def verifies(verifier: str, challenge: str) -> bool:
    """Whether `verifier` is the secret behind `challenge`.

    Compared with `compare_digest` because this decides whether to issue a token
    pair. The values are public-ish and the comparison is short, so the timing
    channel is thin — but it costs nothing to close and the habit is worth more
    than the reasoning about when it does not matter.
    """
    return hmac.compare_digest(challenge_for(verifier), challenge)
