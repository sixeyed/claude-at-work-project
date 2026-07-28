"""Request and response bodies for the Auth API (spec §3.1).

JSON is camelCase across the platform, with no exceptions (Conventions §4) —
including the token endpoints, which spec §3.1 originally wrote in OAuth 2.0
snake_case (`access_token`, `grant_type`). One casing rule that holds everywhere
beats a rule with a carve-out that every client has to remember; these endpoints
are called by our own SPA, not by a stock OAuth library. The design doc has been
updated to match.

Config is a different contract and stays as it is: environment variables are
`SCREAMING_SNAKE_CASE` (Conventions §8), and the JSON inside `AUTH_SERVICE_CLIENTS`
is snake_case like the rest of the settings.

These models stay in the service rather than in `collabhub-contracts`: their
only consumer is the browser, and `contracts` is for models with a producer and
a consumer inside the platform.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Responses: snake_case fields in Python, camelCase on the wire.

    `populate_by_name` is for our side of the boundary — routers construct these
    with Python field names — and costs nothing on output, which always
    serialises through the alias.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CamelRequest(BaseModel):
    """Requests: camelCase only.

    Deliberately *not* `populate_by_name`. Nothing builds a request model in
    Python, so allowing the snake_case field name would only mean accepting a
    second wire format that no document describes — and the endpoint quietly
    tolerating both is how two shapes end up in production.
    """

    model_config = ConfigDict(alias_generator=to_camel)


# --- token endpoints ------------------------------------------------------


class TokenResponse(CamelModel):
    """What a sign-in returns to the browser.

    There is no `refreshToken` field, and its absence is the security control:
    the refresh token is delivered as an `HttpOnly` cookie the SPA cannot read
    (register D22). A token in this body would be in the JS heap, which is
    precisely where injected script could reach it.
    """

    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class ServiceTokenResponse(CamelModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class SwitchWorkspaceRequest(CamelRequest):
    """Only the target. The session comes from the cookie, never the body."""

    workspace_id: uuid.UUID


class ServiceTokenRequest(CamelRequest):
    grant_type: str
    client_id: str
    client_secret: str


class TokenExchangeRequest(CamelRequest):
    """Spend the authorization code the callback handed to the SPA (spec §3.1).

    `codeVerifier` is the PKCE secret the SPA generated before the login began
    and has never transmitted. It is what proves this is the same client that
    started the flow, rather than whoever read the code out of a browser history
    or a referrer header.
    """

    grant_type: str
    code: str
    code_verifier: str


# --- resource endpoints (camelCase) ---------------------------------------


class UserResponse(CamelModel):
    """The caller's own profile. Carries the email; only `/users/me` returns it."""

    id: uuid.UUID
    email: str
    display_name: str
    avatar_asset: uuid.UUID | None
    status: str
    created_at: datetime


class PublicUserResponse(CamelModel):
    """Someone else's profile, for rendering an avatar or a mention.

    Deliberately not `UserResponse` minus a field. Email, status and timestamps
    are absent from the type, so no future edit to the shared model can leak
    them here by accident.
    """

    id: uuid.UUID
    display_name: str
    avatar_asset: uuid.UUID | None


class UpdateUserRequest(CamelRequest):
    """A profile edit. Absent fields are left alone; `null` clears the avatar."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_asset: uuid.UUID | None = None


class AddMemberRequest(CamelRequest):
    """Add an *existing* user to a workspace, by id or by email.

    Not an invitation: there is no invitations table, so an email that belongs to
    nobody is a 404 rather than a pending invite. Inviting someone who has never
    signed in needs a table, a delivery channel and an expiry policy — its own
    decision, not something to imply here.
    """

    user_id: uuid.UUID | None = None
    email: EmailStr | None = None
    role: str = "member"

    @model_validator(mode="after")
    def _exactly_one_subject(self) -> Self:
        if (self.user_id is None) == (self.email is None):
            raise ValueError("provide exactly one of userId or email")
        return self


class UpdateMemberRequest(CamelRequest):
    role: str


class MemberResponse(CamelModel):
    user: PublicUserResponse
    role: str
    joined_at: datetime


class MemberListResponse(CamelModel):
    items: list[MemberResponse]
    next_cursor: str | None = None


class WorkspaceResponse(CamelModel):
    id: uuid.UUID
    name: str
    role: str


class WorkspaceListResponse(CamelModel):
    """The list envelope from Conventions §4.1.

    `nextCursor` is always null: a user's own memberships are a bounded list —
    the workspace switcher shows all of them — so there is nothing to page
    through. The envelope stays consistent with every other list on the platform.
    """

    items: list[WorkspaceResponse]
    next_cursor: str | None = None


class UserInfoResponse(BaseModel):
    """The current token's claims, under their claim names (spec §3)."""

    sub: str
    name: str
    email: str
    wsp: str
    roles: list[str]
