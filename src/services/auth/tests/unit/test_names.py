"""The display-name rules (gh-5, issue Req 1 to 4).

`auth.names` is one pure module used by `PATCH /users/me`, by `provision_user` and
by migration 0002, so the rules are proven here once, with no database: trimming
and NFC, the refused characters, the comparison key, the `X 2` suffix rule and the
duplicate renamer.

Special characters are built with `chr()` or `\\x` escapes, never typed: an invisible
or ambiguous character in a source file is the very thing these rules are about.
"""

from __future__ import annotations

import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from itertools import islice

import pytest

from auth import names
from auth.models import User

REQUIRED = "A display name is required."
TOO_LONG = "A display name can be at most 100 characters."
INVISIBLE = "A display name can't contain invisible or control characters."

ZWSP = chr(0x200B)  # zero width space (Cf)
ZWNJ = chr(0x200C)
ZWJ = chr(0x200D)
CGJ = chr(0x034F)  # combining grapheme joiner (default-ignorable)
HANGUL_FILLER = chr(0x3164)  # default-ignorable
NBSP = "\xa0"
IDEOGRAPHIC_SPACE = chr(0x3000)
BRAILLE_BLANK = chr(0x2800)  # a visible symbol that renders blank: allowed (Decided 5)
ACUTE = chr(0x0301)  # combining acute accent
E_ACUTE = "\xe9"  # the precomposed e-acute
CAP_E_ACUTE = "\xc9"
SHARP_S = "\xdf"
A_ACUTE = "\xe1"
DIAERESIS_E = "\xeb"
EMOJI = chr(0x1F600)

JOSE_PRECOMPOSED = "Jos" + E_ACUTE
JOSE_DECOMPOSED = "Jose" + ACUTE

# Unicode 15.0 (Python 3.12's `unidata_version`). The first and last code point of each
# default-ignorable range, written out here so the test does not borrow the table it
# checks.
IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
REFUSED_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def row(
    n: int, display_name: str, *, age: int | None = None, email: str | None = None, id_=None
) -> names.NameRow:
    """A row created `age` minutes after T0 (default: `n`)."""
    return names.NameRow(
        id=id_ or uuid.UUID(int=n),
        created_at=T0 + timedelta(minutes=n if age is None else age),
        display_name=display_name,
        email=email or f"user{n}@example.com",
    )


def refusal(raw: str) -> str:
    with pytest.raises(names.InvalidNameError) as caught:
        names.clean(raw)
    return str(caught.value)


# --------------------------------------------------------------------------
# Req 1 - what is stored
# --------------------------------------------------------------------------


def test_a_name_is_trimmed_and_composed() -> None:
    """Without this a name keeps its padding, or `e` + U+0301 and e-acute are two names."""
    assert JOSE_DECOMPOSED != JOSE_PRECOMPOSED
    assert names.clean("  " + JOSE_DECOMPOSED + "  ") == JOSE_PRECOMPOSED
    assert names.clean("Ada  Lovelace") == "Ada  Lovelace"
    assert names.clean(NBSP + "Ada" + IDEOGRAPHIC_SPACE) == "Ada"
    assert names.normalise("  " + JOSE_DECOMPOSED + "  ") == JOSE_PRECOMPOSED


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("Grace" + ZWSP, INVISIBLE),
        ("Grace" + HANGUL_FILLER, INVISIBLE),
        ("Gr" + CGJ + "ace", INVISIBLE),
        ("Grace\x07", INVISIBLE),
        (" ", REQUIRED),
        (NBSP, REQUIRED),
        ("", REQUIRED),
    ],
    ids=["zwsp", "hangul-filler", "cgj", "bell", "space", "nbsp", "empty"],
)
def test_each_refused_example_is_refused(raw: str, message: str) -> None:
    """Each of the issue's refused names is a 400 with its own message."""
    assert refusal(raw) == message


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        (JOSE_PRECOMPOSED, JOSE_PRECOMPOSED),
        (JOSE_DECOMPOSED, JOSE_PRECOMPOSED),
        ("Zo" + DIAERESIS_E, "Zo" + DIAERESIS_E),
        ("李小龍", "李小龍"),
        ("O'Brien", "O'Brien"),
        ("Ada  Lovelace", "Ada  Lovelace"),
        (BRAILLE_BLANK + "Ada", BRAILLE_BLANK + "Ada"),
    ],
    ids=["precomposed", "decomposed", "diaeresis", "cjk", "apostrophe", "inner-spaces", "braille"],
)
def test_each_accepted_example_is_accepted(raw: str, stored: str) -> None:
    """The refusal rule must not catch real names; U+2800 stays allowed (Decided 5)."""
    assert names.clean(raw) == stored


@pytest.mark.parametrize(
    "char",
    [
        "\x1f",  # Cc
        chr(0x2066),  # Cf
        chr(0xD800),  # Cs
        chr(0xE000),  # Co
        chr(0x0378),  # Cn
        chr(0x2028),  # Zl
        chr(0x2029),  # Zp
    ],
    ids=["Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"],
)
def test_one_character_of_each_refused_category_is_refused(char: str) -> None:
    """Each category on its own, mid-name where trimming cannot hide it."""
    assert unicodedata.category(char) in REFUSED_CATEGORIES
    assert refusal(f"Gr{char}ace") == INVISIBLE


@pytest.mark.parametrize(("first", "last"), IGNORABLE_RANGES)
def test_every_default_ignorable_range_is_refused_at_both_ends(first: int, last: int) -> None:
    """An off-by-one in the table lets the first or last code point of a range through.

    Where the neighbour just outside is refused for another reason (Cn, Cf) it is
    skipped; the others must be accepted, or the table is too wide.
    """
    for point in (first, last):
        assert refusal(f"Gr{chr(point)}ace") == INVISIBLE, hex(point)

    for point in (first - 1, last + 1):
        char = chr(point)
        if unicodedata.category(char) in REFUSED_CATEGORIES:
            continue
        stored = names.clean(f"Gr{char}ace")
        assert stored == unicodedata.normalize("NFC", f"Gr{char}ace"), hex(point)


def test_the_outside_neighbours_the_table_is_tested_against_exist() -> None:
    """Guards the guard above: enough neighbours are allowed, so it checks something."""
    allowed = [
        point
        for first, last in IGNORABLE_RANGES
        for point in (first - 1, last + 1)
        if unicodedata.category(chr(point)) not in REFUSED_CATEGORIES
    ]
    assert len(allowed) >= 15
    for point in (0x3163, 0x3165, 0x2070):
        assert point in allowed
        assert names.clean(f"Gr{chr(point)}ace")


def test_the_zero_width_joiner_is_refused() -> None:
    """Decided 5: ZWJ and ZWNJ go with the rest of the default-ignorables."""
    assert refusal("Gr" + ZWJ + "ace") == INVISIBLE
    assert refusal("Gr" + ZWNJ + "ace") == INVISIBLE


def test_length_counts_after_trimming() -> None:
    """The limit is on the stored form, in code points, not on what was typed."""
    assert names.clean(" " + "a" * 100 + " ") == "a" * 100
    assert refusal("a" * 101) == TOO_LONG
    assert refusal(" " + "a" * 101 + " ") == TOO_LONG
    assert refusal("") == REQUIRED
    assert names.clean(EMOJI * 100) == EMOJI * 100
    assert refusal(EMOJI * 101) == TOO_LONG


def test_check_works_on_an_already_normalised_name() -> None:
    """`check` is the rule without the normalising: fine names pass, bad ones raise."""
    names.check("Ada")
    with pytest.raises(names.InvalidNameError, match="invisible"):
        names.check("Grace" + ZWSP)
    assert names.MAX_LENGTH == 100


# --------------------------------------------------------------------------
# Req 2 - the comparison key
# --------------------------------------------------------------------------


def test_the_key_ignores_case_and_normal_form() -> None:
    """Two spellings of one name must share a key, or the index lets both in."""
    keys = {
        names.name_key(JOSE_PRECOMPOSED),
        names.name_key("JOS" + CAP_E_ACUTE),
        names.name_key("jos" + E_ACUTE),
        names.name_key(JOSE_DECOMPOSED),
    }
    assert keys == {"jos" + E_ACUTE}
    assert names.name_key("Stra" + SHARP_S + "e") == names.name_key("STRASSE")
    assert names.name_key("Ada") != names.name_key("Ad" + A_ACUTE)
    assert names.name_key("Ada") != names.name_key("Adam")


# --------------------------------------------------------------------------
# Req 3 - suffixes
# --------------------------------------------------------------------------


def test_candidates_count_from_two() -> None:
    assert list(islice(names.candidates("X"), 3)) == ["X", "X 2", "X 3"]


def test_candidates_cut_the_base_to_fit() -> None:
    """A suffix may not push a name past the limit Req 1 enforces."""
    produced = list(islice(names.candidates("a" * 100), 10))

    assert produced[0] == "a" * 100
    assert produced[1] == "a" * 98 + " 2"
    assert len(produced[1]) == 100
    assert produced[9] == "a" * 97 + " 10"
    assert all(len(c) <= 100 for c in produced)


def test_first_free_skips_taken_names_ignoring_case() -> None:
    assert names.first_free("Sam", {"sam", "sam 2"}) == "Sam 3"
    assert names.first_free("SAM", {"sam"}) == "SAM 2"
    assert names.first_free("Sam", set()) == "Sam"
    assert names.first_free("Sam", {"sam 2"}) == "Sam"


def test_provisional_drops_refused_characters_and_truncates() -> None:
    assert names.provisional("Gr" + ZWSP + "ace", "zed") == "Grace"
    assert names.provisional("a" * 120, "zed") == "a" * 100
    assert names.provisional("  " + JOSE_DECOMPOSED + " ", "zed") == JOSE_PRECOMPOSED


def test_provisional_falls_back_to_the_email_then_user() -> None:
    assert names.provisional(ZWSP, "zed") == "zed"
    assert names.provisional("   ", "ze" + ZWSP + "d") == "zed"
    assert names.provisional(ZWSP, ZWSP) == "user"
    assert names.provisional("", "") == "user"
    for raw, fallback in [(ZWSP, "zed"), (ZWSP, ZWSP), ("a" * 120, "x")]:
        names.check(names.provisional(raw, fallback))


# --------------------------------------------------------------------------
# Req 4 - existing duplicates
# --------------------------------------------------------------------------


def test_dedupe_keeps_the_oldest_and_suffixes_the_rest_by_age() -> None:
    """Each duplicate keeps its own spelling as the base of its suffix."""
    first, second, third = row(0, "Sam"), row(1, " sam"), row(2, "SAM")

    renamed = names.dedupe([third, first, second])

    assert renamed == {first.id: "Sam", second.id: "sam 2", third.id: "SAM 3"}


def test_dedupe_breaks_a_created_at_tie_on_id() -> None:
    low = row(1, "Sam", age=5, id_=uuid.UUID(int=1))
    high = row(2, "sam", age=5, id_=uuid.UUID(int=2))

    assert names.dedupe([high, low]) == {low.id: "Sam", high.id: "sam 2"}
    assert names.dedupe([low, high]) == {low.id: "Sam", high.id: "sam 2"}


def test_dedupe_sees_duplicates_only_after_normalising() -> None:
    old, new = row(0, JOSE_DECOMPOSED), row(1, JOSE_PRECOMPOSED)

    assert names.dedupe([old, new]) == {old.id: JOSE_PRECOMPOSED, new.id: JOSE_PRECOMPOSED + " 2"}


def test_dedupe_skips_a_suffix_someone_already_holds() -> None:
    sam, sam2, newer = row(0, "Sam"), row(1, "Sam 2"), row(2, "sam")

    assert names.dedupe([sam, sam2, newer]) == {sam.id: "Sam", sam2.id: "Sam 2", newer.id: "sam 3"}


def test_dedupe_never_renames_a_newer_name_that_was_no_duplicate() -> None:
    """Reserve first, then suffix.

    A build that assigns purely by age gives the newer `sam` the suffix `2` and then
    has to rename `Sam 2` to `Sam 2 2` (Decision 17a).
    """
    sam, dupe, held = row(0, "Sam"), row(1, "sam"), row(2, "Sam 2")

    renamed = names.dedupe([sam, dupe, held])

    assert renamed == {sam.id: "Sam", dupe.id: "sam 3", held.id: "Sam 2"}


def test_dedupe_repairs_a_name_check_refuses() -> None:
    blank = row(0, "   ", email="zed@x")

    assert names.dedupe([blank]) == {blank.id: "zed"}


def test_dedupe_leaves_distinct_names_as_they_are() -> None:
    """Every row is in the answer, a unique one under its normalised name."""
    ada, grace = row(0, " Ada"), row(1, "Grace")

    assert names.dedupe([ada, grace]) == {ada.id: "Ada", grace.id: "Grace"}


# --------------------------------------------------------------------------
# The key follows the name on the model (Decision 12)
# --------------------------------------------------------------------------


def test_setting_a_users_display_name_sets_its_key() -> None:
    """No ORM writer can forget the key: assigning the name sets it, no session needed."""
    user = User(id=uuid.uuid4(), email="jose@example.com", display_name=JOSE_PRECOMPOSED)
    assert user.display_name_key == "jos" + E_ACUTE

    user.display_name = "ADA"
    assert user.display_name_key == "ada"

    user.display_name = JOSE_DECOMPOSED
    assert user.display_name_key == "jos" + E_ACUTE
