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

from pydantic import BaseModel, ConfigDict, EmailStr
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
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class ServiceTokenResponse(CamelModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class RefreshRequest(CamelRequest):
    refresh_token: str


class SwitchWorkspaceRequest(CamelRequest):
    refresh_token: str
    workspace_id: uuid.UUID


class ServiceTokenRequest(CamelRequest):
    grant_type: str
    client_id: str
    client_secret: str


class DevLoginRequest(CamelRequest):
    """Local-only sign-in. No credential, because there is nothing to check."""

    email: EmailStr
    display_name: str | None = None


class LogoutRequest(CamelRequest):
    refresh_token: str | None = None


# --- resource endpoints (camelCase) ---------------------------------------


class UserResponse(CamelModel):
    id: uuid.UUID
    email: str
    display_name: str
    avatar_asset: uuid.UUID | None
    status: str
    created_at: datetime


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
