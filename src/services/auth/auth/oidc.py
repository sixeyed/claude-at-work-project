"""Talking to an upstream OpenID Connect provider (spec §5.1, register D5).

This service is a relying party. It sends the user to a provider, takes back a
code, and turns the resulting id_token into a CollabHub identity. It is never a
provider itself — nothing here issues a token, and `/.well-known/jwks.json` in
this service is about CollabHub's own signing keys, not these.

Everything in this module is about *not* trusting what comes back:

* the id_token is verified by signature against the provider's JWKS, not read;
* `iss` must equal the provider's public authority, so a token minted by some
  other provider we also happen to trust cannot be replayed here;
* `nonce` must match the one generated for this specific login, which is what
  stops an id_token obtained elsewhere being injected into someone's callback.

The public/internal authority split (see `OidcProvider`) shows up in one place:
discovery is fetched over the back channel and its `issuer` is checked against
the *public* authority, then the endpoints it advertises — which the provider
derives from its issuer, so they point at the public host — are rewritten onto
the back-channel base before this process calls them.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from auth.settings import OidcProvider
from shared import JwksClient

DISCOVERY_PATH = "/.well-known/openid-configuration"
HTTP_TIMEOUT_SECONDS = 10.0


class ProviderError(Exception):
    """The provider is misconfigured, unreachable, or answered nonsensically.

    Distinct from a bad credential: this is our problem or theirs, not the
    user's, and it must not be reported as a failed sign-in.
    """


class IdentityRejectedError(Exception):
    """The provider answered, but the answer cannot be accepted as an identity."""


@dataclass(frozen=True)
class ProviderMetadata:
    """The three endpoints this service uses, already pointed at the right host."""

    authorization_endpoint: str  # public — the browser goes here
    token_endpoint: str  # back channel
    jwks_uri: str  # back channel


@dataclass(frozen=True)
class FederatedIdentity:
    """A verified upstream identity, in the terms this service stores."""

    provider: str
    subject: str
    email: str
    email_verified: bool
    display_name: str

    @property
    def provider_key(self) -> str:
        """How the provider is written in `external_identities` (spec §4)."""
        return f"oidc:{self.provider}"


class OidcClient:
    """One upstream provider, with its discovery document and keys cached.

    Discovery and JWKS are fetched lazily rather than at startup: a provider
    that is briefly down should delay the first sign-in, not stop this service
    from starting and taking traffic on every other endpoint it serves.
    """

    def __init__(self, provider: OidcProvider, *, http: httpx.AsyncClient | None = None) -> None:
        self._provider = provider
        self._http = http or httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
        self._metadata: ProviderMetadata | None = None
        self._jwks: JwksClient | None = None
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._provider.name

    async def metadata(self) -> ProviderMetadata:
        async with self._lock:
            if self._metadata is None:
                self._metadata = await self._discover()
            return self._metadata

    async def _discover(self) -> ProviderMetadata:
        url = self._provider.back_channel + DISCOVERY_PATH
        try:
            response = await self._http.get(url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"discovery failed for {self._provider.name}: {exc}") from exc

        issuer = str(document.get("issuer", "")).rstrip("/")
        if issuer != self._provider.front_channel:
            # The provider's own idea of its identity disagrees with ours, so
            # every `iss` check downstream would fail anyway — and pointing at
            # the wrong provider entirely looks exactly like this.
            raise ProviderError(
                f"{self._provider.name} advertises issuer {issuer!r}, "
                f"but is configured as {self._provider.front_channel!r}"
            )

        try:
            return ProviderMetadata(
                authorization_endpoint=document["authorization_endpoint"],
                token_endpoint=self._to_back_channel(document["token_endpoint"]),
                jwks_uri=self._to_back_channel(document["jwks_uri"]),
            )
        except KeyError as exc:
            raise ProviderError(f"discovery document is missing {exc}") from exc

    def _to_back_channel(self, url: str) -> str:
        """Re-point a discovered endpoint at the address this process can reach.

        The provider builds these from its issuer, so they carry the public
        host. Swapping only the configured prefix — rather than rewriting the
        host generally — means a provider that returns an endpoint somewhere
        unexpected is left alone and fails loudly instead of being silently
        redirected somewhere it never asked for.
        """
        public = self._provider.front_channel
        if url.startswith(public):
            return self._provider.back_channel + url[len(public) :]
        return url

    async def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, code_challenge: str
    ) -> str:
        """Where to send the browser to begin a login."""
        metadata = await self.metadata()
        query = urlencode(
            {
                "client_id": self._provider.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(self._provider.scopes),
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        separator = "&" if "?" in metadata.authorization_endpoint else "?"
        return f"{metadata.authorization_endpoint}{separator}{query}"

    async def exchange(
        self, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> FederatedIdentity:
        """Trade the provider's code for an id_token, and verify it."""
        metadata = await self.metadata()
        try:
            response = await self._http.post(
                metadata.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                    "client_id": self._provider.client_id,
                    "client_secret": self._provider.client_secret,
                },
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"token exchange failed: {exc}") from exc

        if response.status_code != httpx.codes.OK:
            # A 4xx here is the provider refusing the code — expired, already
            # spent, or issued to someone else. That is a rejected sign-in, not
            # an outage.
            raise IdentityRejectedError(f"provider refused the code ({response.status_code})")

        body = response.json()
        id_token = body.get("id_token")
        if not id_token:
            raise ProviderError("token response carried no id_token")

        return self._identity_from(await self._verify(id_token, nonce=nonce))

    async def _verify(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        if self._jwks is None:
            metadata = await self.metadata()
            self._jwks = JwksClient(metadata.jwks_uri, http_client=self._http)

        try:
            header = jwt.get_unverified_header(id_token)
            key = await self._jwks.key_for(header.get("kid"))
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self._provider.client_id,
                issuer=self._provider.front_channel,
            )
        except Exception as exc:
            # Signature, `iss`, `aud` and expiry all land here. Which one failed
            # is useful to whoever forged the token and to nobody else.
            raise IdentityRejectedError(f"id_token rejected: {exc}") from exc

        if claims.get("nonce") != nonce:
            # The token is validly signed but belongs to a different login. This
            # is what an injected id_token looks like.
            raise IdentityRejectedError("id_token nonce does not match this login")

        return claims

    def _identity_from(self, claims: dict[str, Any]) -> FederatedIdentity:
        subject = claims.get("sub")
        email = claims.get("email")
        if not subject or not email:
            # Without a stable subject there is nothing to link an account to,
            # and without an email there is no account to create.
            raise IdentityRejectedError("id_token carried no subject or no email")

        return FederatedIdentity(
            provider=self._provider.name,
            subject=str(subject),
            email=str(email),
            email_verified=bool(claims.get("email_verified", False)),
            # Providers vary on which of these they send; the local part of the
            # email is a better placeholder than a blank name.
            display_name=str(
                claims.get("name") or claims.get("preferred_username") or email.split("@")[0]
            ),
        )

    async def aclose(self) -> None:
        await self._http.aclose()


def build_clients(providers: list[OidcProvider]) -> dict[str, OidcClient]:
    """One client per configured provider, keyed by the name used in the URL."""
    return {provider.name: OidcClient(provider) for provider in providers}
