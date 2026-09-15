"""Who may edit and who may delete a message — the policies, not the routes.

The first worked example of register D32's decision 2: the rule is a pure
function over a row that is already loaded, so it needs no session and nothing
faked. That a route *applies* it, and maps each refusal to its status, is
proven once per route in `tests/integration/test_messages.py`.

Visibility is not here. It is a SQL predicate (`_visible`), and a message the
caller cannot see never reaches these functions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from messaging.messages import (
    AlreadyDeletedError,
    NotAuthorError,
    NotDeletableError,
    check_deletable,
    check_editable,
)

ADA = uuid.uuid4()
GRACE = uuid.uuid4()
DELETED_AT = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)


# --- edit ------------------------------------------------------------------


def test_the_author_may_edit(a_message):
    """Breaks if the author check compares the wrong ids."""
    check_editable(a_message(author_id=ADA), user_id=ADA)


def test_someone_else_may_not_edit(a_message):
    """Breaks if editing is opened to anyone who can see the message."""
    with pytest.raises(NotAuthorError):
        check_editable(a_message(author_id=GRACE), user_id=ADA)


def test_a_deleted_message_cannot_be_edited_even_by_its_author(a_message):
    """Breaks if the state check is dropped — a tombstone would take new text."""
    with pytest.raises(AlreadyDeletedError):
        check_editable(a_message(author_id=ADA, deleted_at=DELETED_AT), user_id=ADA)


def test_a_deleted_message_of_graces_says_deleted_before_not_yours(a_message):
    """State before authorship: breaks if the two checks swap order.

    `edit` has always checked in this order, and the integration suite's 409
    for "editing a deleted message" depends on it.
    """
    with pytest.raises(AlreadyDeletedError):
        check_editable(a_message(author_id=GRACE, deleted_at=DELETED_AT), user_id=ADA)


# --- delete ----------------------------------------------------------------


def test_the_author_may_delete(a_message):
    """Breaks if deleting your own message needs the admin role."""
    check_deletable(a_message(author_id=ADA), user_id=ADA, is_channel_admin=False)


def test_a_channel_admin_may_delete_someone_elses(a_message):
    """Moderation (D8d): breaks if the admin branch is dropped."""
    check_deletable(a_message(author_id=GRACE), user_id=ADA, is_channel_admin=True)


def test_someone_who_is_neither_may_not_delete(a_message):
    """Breaks if deleting is opened to anyone who can see the message."""
    with pytest.raises(NotDeletableError):
        check_deletable(a_message(author_id=GRACE), user_id=ADA, is_channel_admin=False)


def test_deleting_an_already_deleted_message_is_not_a_permission_error(a_message):
    """A repeat delete returns the existing tombstone (D8d), so the policy is silent.

    Breaks if the delete policy borrows the edit policy's state check.
    """
    check_deletable(
        a_message(author_id=ADA, deleted_at=DELETED_AT), user_id=ADA, is_channel_admin=False
    )
