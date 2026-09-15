"""UUID v7 generation (Conventions §3).

The property that matters is time-ordering: IDs generated later must sort after
IDs generated earlier, because cursor pagination and every `ORDER BY id` in the
platform depend on it.
"""

import uuid

from shared import uuid7


def test_is_a_version_7_uuid() -> None:
    value = uuid7()

    assert isinstance(value, uuid.UUID)
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_ids_generated_in_sequence_sort_in_generation_order() -> None:
    ids = [uuid7() for _ in range(1000)]

    assert ids == sorted(ids)


def test_ids_are_unique() -> None:
    ids = [uuid7() for _ in range(1000)]

    assert len(set(ids)) == len(ids)


def test_encodes_the_current_time_in_the_leading_48_bits() -> None:
    import time

    before_ms = int(time.time() * 1000)
    value = uuid7()
    after_ms = int(time.time() * 1000)

    encoded_ms = int.from_bytes(value.bytes[:6], "big")

    assert before_ms <= encoded_ms <= after_ms
