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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

#: Static outer bound on a message body, shared by send and edit.
#:
#: **Not the rule.** The rule is `MESSAGING_MAX_BODY_CHARS`, checked in the
#: domain so the message can name the limit that was broken. This exists only to
#: stop an unbounded string reaching the domain at all, and it must stay well
#: above the configured limit — otherwise raising that setting would silently
#: start reporting a generic Pydantic error from the wrong layer.
#:
#: One constant, because send and edit disagreeing on how long a message may be
#: is a bug with a very long half-life.
MAX_BODY_FIELD_LENGTH = 64_000


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


class UpdateChannelRequest(CamelRequest):
    """Rename a channel, or change its topic.

    `version` is required and is the version the client last read. The expected
    version travels in the body rather than in an `If-Match` header: nothing on
    this platform emits or parses an ETag, and the `Channel` DTO already carries
    the number the SPA holds in its cache.

    There is no `archivedAt`. Archiving is `DELETE /channels/{id}`, so no client
    ever writes a server clock into a timestamp column.

    An absent `topic` leaves the topic alone; an explicit `null` clears it. The
    router tells them apart with `model_fields_set`, which is why the two cases
    do not need two fields.
    """

    version: int
    name: str | None = Field(default=None, max_length=200)
    topic: str | None = Field(default=None, max_length=500)


class AddChannelMemberRequest(CamelRequest):
    """Add one person to a channel, by id.

    Singular, not "add member(s)": a batch add has no honest status code when
    three of five ids are already in the channel. Five calls do.

    By id and never by email, because Messaging owns no user records and must
    not read Auth's tables (Conventions §2) — it cannot resolve an address, and
    it does not check that the id names a real user either. The browser holds a
    token entitling it to both services and does the resolving.
    """

    user_id: uuid.UUID
    role: Literal["admin", "member"] = "member"


class ChannelMemberResponse(CamelModel):
    """One membership row. A bare `userId`: there is no name here to give.

    The SPA renders the name by looking the id up in Auth's workspace member
    list, which it is already entitled to read.
    """

    user_id: uuid.UUID
    role: str
    joined_at: datetime


class ChannelMemberListResponse(CamelModel):
    items: list[ChannelMemberResponse]
    next_cursor: str | None = None


class MessageResponse(CamelModel):
    """A message as the API reports it (spec §3.1.3).

    Two absences and one presence are all deliberate.

    No `reactions`. The design doc has the key; the table does not exist and no
    query makes it, and a field that is always `[]` is a claim the service does
    not honour. `attachments` looks like the same case and is not — it is a real
    column read off a real row that happens to be empty, because the Asset
    service is a skeleton rather than because nothing was built.

    No `workspaceId`, for the reason `ChannelResponse` gives: it is the token's
    `wsp` claim, and echoing it invites a client to start sending it.

    `authorId` is a bare id and there is no user expansion. Messaging owns no
    user records and must not read Auth's tables (Conventions §2); the browser
    resolves the name from Auth's own workspace directory, holding a token that
    already entitles it to both.

    **`body` is `""` on a deleted message, never `null` and never the original
    text.** The redaction is server-side and the type stays non-null, so the
    generated TypeScript does not force a null check at every render site. The
    client renders "this message was deleted" from `deletedAt`, not from an
    empty body.
    """

    id: uuid.UUID
    channel_id: uuid.UUID
    author_id: uuid.UUID
    thread_root_id: uuid.UUID | None
    body: str
    attachments: list[uuid.UUID]
    created_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None
    version: int


class MessageListResponse(CamelModel):
    """The list envelope from Conventions §4.1. Newest first."""

    items: list[MessageResponse]
    next_cursor: str | None = None


class SendMessageRequest(CamelRequest):
    """Say something in a channel.

    Carries the body and nothing else. No `channelId` — it is in the path; no
    `authorId` — it is the token's `sub`; no `threadRootId` and no
    `attachmentIds`, because accepting a field the service ignores is a claim it
    does not honour. Both arrive with the features that need them.

    `max_length` here is a static outer bound and **not** the rule — see
    `MAX_BODY_FIELD_LENGTH`.
    """

    body: str = Field(max_length=MAX_BODY_FIELD_LENGTH)


class EditMessageRequest(CamelRequest):
    """Rewrite a message.

    **Not a JSON Merge Patch of `Message`.** Conventions §4 defines `PATCH` that
    way, and under RFC 7386 `{"version": 3}` would mean *assign 3 to version* —
    the exact opposite of what it means here. `version` is a precondition: the
    version the caller last saw, which the server checks and refuses on.

    Both fields are required. There is exactly one editable field on a message,
    so "absent means leave it alone" has nothing to express — the
    `model_fields_set` idiom `UpdateChannelRequest` needs is deliberately not
    used here, rather than forgotten.

    `max_length` is `MAX_BODY_FIELD_LENGTH`, the same bound `SendMessageRequest`
    carries — one constant, not two numbers to drift apart.
    """

    body: str = Field(max_length=MAX_BODY_FIELD_LENGTH)
    version: int
