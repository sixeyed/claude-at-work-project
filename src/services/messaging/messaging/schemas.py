"""Request and response bodies for the Messaging API (spec §3.1).

JSON is camelCase across the platform (Conventions §4); SQL is snake_case. These
models stay in the service rather than in `collabhub-contracts`, which is for
models with a producer *and* a consumer inside the platform — the only consumer
of these is the browser.

The design doc specifies a `Message` DTO and no `Channel` DTO; this file is
where that gap was closed, and doc 02 §3.1 has been updated to match.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Responses: snake_case fields in Python, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CamelRequest(BaseModel):
    """Requests: camelCase only.

    Deliberately *not* `populate_by_name`. Nothing builds a request model in
    Python, so allowing the snake_case field name would only mean accepting a
    second wire format that no document describes.
    """

    model_config = ConfigDict(alias_generator=to_camel)


class ChannelResponse(CamelModel):
    """A channel as the API reports it.

    No `workspaceId`: a channel is always in the workspace named by the caller's
    `wsp` claim, and echoing it back invites a client to start sending it.

    `version` and `myRole` are unused by the create-and-list surface. They ship
    now because the alternative is changing this shape again one slice later —
    `version` is what an edit sends back for optimistic concurrency, and
    `myRole` is what decides whether the UI offers the admin controls.
    """

    id: uuid.UUID
    name: str
    topic: str | None
    kind: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    version: int
    my_role: str | None = None


class ChannelListResponse(CamelModel):
    """The list envelope from Conventions §4.1."""

    items: list[ChannelResponse]
    next_cursor: str | None = None


class CreateChannelRequest(CamelRequest):
    """Create a channel in the caller's workspace.

    `name` is checked in the domain rather than by a Pydantic pattern, so every
    broken rule gets its own message in the `errors` map instead of one opaque
    "string does not match regex". Only the outer bound is here, to keep an
    unbounded body from reaching the domain at all.
    """

    name: str = Field(max_length=200)
    topic: str | None = Field(default=None, max_length=500)
    kind: str = "public"
