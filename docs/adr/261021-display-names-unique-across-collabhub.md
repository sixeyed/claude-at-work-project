# Display names are unique across CollabHub

- **Status:** Accepted
- **Date:** 2026-10-21

## Context

A name on a message should mean one person. Until now any number of users could share a display name
and `PATCH /users/me` accepted anything non-empty up to 100 characters, including names made of
invisible characters (register D46, issue gh-5). Users belong to many workspaces and are renamed by
themselves only, so the scope has to be global: the same person is the same name wherever they are.

## Decision

Display names are unique across all of CollabHub, ignoring case and Unicode form, **deleted accounts
included** — a deleted user's name stays taken.

- A name is trimmed and NFC-normalised, then must be 1–100 code points and contain no control,
  format, surrogate, private-use, unassigned, line/paragraph-separator or `Default_Ignorable`
  character (ZWJ and ZWNJ included). U+2800 stays allowed. One module, `auth.names`, holds these
  rules and is used by `PATCH /users/me`, by `provision_user` and by migration `0002`.
- Uniqueness is decided on `users.display_name_key`, `NFC(NFD(name).casefold())`, which the
  application computes (a SQLAlchemy `@validates` on the model) and a unique index
  `uq_users_display_name_key` enforces. The index settles every race; `update_me` maps its conflict
  at commit to a 409, and `provision_user` inserts in a SAVEPOINT and takes the next suffix when the
  name has meanwhile been taken.
- A taken name is `409` with `detail` and `errors.displayName` both `"That name is already taken."`.
  It names nobody and no workspace.
- A first sign-in never fails over a name: an unusable IdP name is repaired, and a taken one becomes
  `X 2`, `X 3` … (the base cut so the result stays within 100).
- Migration `0002` normalised existing names and renamed every duplicate but the oldest the same way,
  reserving the names that were never duplicates first so none of them is renamed to make room. It is
  one-way.

## Consequences

- **A deliberate exception to the 404 rule** (Conventions §5.4): a 409 reveals that the name is held
  by someone, perhaps in another workspace. It is accepted — the alternative is to let two people
  share a name. Recorded in Conventions §5.4.
- Case folding is full, not `lower()`: `Straße` and `STRASSE` collide. Confusables (a Cyrillic `а` for
  a Latin `a`) are not handled.
- `0002` imports `auth.names`; a later edit to it changes what a fresh run of the migration does.
- Renames reach other people's screens at their next directory fetch (doc 06 §5.2); the renamer's own
  tab updates at once.

## Alternatives considered

- **A unique index on `lower(display_name)`** — the database would compare with rules that depend on
  `LC_CTYPE` (ASCII-only under `C`) and are not case folding, while the application would need its own
  copy of the comparison. One function and one stored key compare one way.
- **Unique per workspace** — a person would be two names across workspaces, and a name in a shared
  channel could mean two people.
- **Letting deleted accounts' names be reused** — an old message would then appear to be written by the
  new holder.
- **Locking instead of an index** — advisory locks would serialise every sign-in.
