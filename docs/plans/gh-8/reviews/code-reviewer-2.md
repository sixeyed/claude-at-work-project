# Code review — gh-8, round 2: approved

Round 1's single finding was a major in the record: doc 06 claimed more about focus than the
code does. It is fixed, and the new wording matches `MessageActions.tsx`. Nothing that feeds a
test layer has changed since the evidence in `docs/test-report.md` was produced, so round 1's
green results still hold for this tree. No critical or major finding is open.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Doc 06 *Focus when "⋯" goes away* promised the fallback, "never the body", on a role change and on the thread closing (major) | Rewrote the bullet. A live delete moves focus to the fallback. A change to the offered actions keeps "⋯", closes the menu and returns focus to "⋯". Closing the thread or switching channel takes the menu with it and claims nothing about focus. | **resolved**. Each claim is checked against the code below. |
| Surviving mutants M1/M3/M4/M5 | Gaps in the approved tests, not in the code | Agreed. They were never findings against the writer and stay under *Unpinned*. |
| Lint not rerun ("Bash was denied") | — | Let go. The lint layer is ruff and eslint, and `scripts/test.sh` lints no Markdown, so a change to `.md` files alone feeds no layer. |

## What ran

- `git diff --stat b250260 HEAD` (round 1's review commit against the round-2 writer's commit):
  `docs/design/06-frontend-spa.md`, the green report, and the runner's `run/` files. Nothing
  else changed.
- `git diff --name-only 9dfde14 HEAD`: `docs/test-report.md` was written at `9dfde148e3b1-dirty`.
  The only paths changed since then are the round-1 build, which that report covers, and
  Markdown. No layer was left stale (*A rework pass*).
- `git status --short`: clean before this review was written.
- I read the claims in the new bullet against `MessageActions.tsx`:
  - **Live delete → fallback.** The layout cleanup at `:174-183` focuses
    `closest('[data-focus-fallback]')`, but only when focus was on "⋯" or in the menu. "When '⋯'
    goes away" names exactly that case. The fallbacks are `MessageList.tsx:302` and
    `ThreadPanel.tsx:140`.
  - **Role change.** `:162-168` compares the actions by value. It calls `close()` only if this
    instance is the open one, and `close()` returns focus to "⋯". This matches "keeps '⋯' and
    closes the menu, returning focus to '⋯'".
  - **Thread closing / channel switch.** The doc no longer claims anything about focus. That
    matches round 1's probe P6, where focus ends on the body.
- A grep for `never the body|thread closing|role change` over `docs/design` and the ADR found no
  other copy of the old claim.
- No sketch or mutant was rerun. The change is to the doc only, and no code path it describes
  has changed.

## Findings

None.

## Unpinned

Carried over from round 1, unchanged. Only reading protects these:

- **M1: the emoji mode is reset on reopen.** `toggle` sets `'menu'` before it opens the menu.
- **M3: the document listeners are attached only while the menu is open** (`if (!open) return`,
  `:130`).
- **M4: an actions change closes the menu only when it is open** (`:167`).
- **M5: the menu is re-placed on the swap to the emoji row.**
- **Listeners are removed with the same capture flag they were added with**, and the horizontal
  clamp behaves correctly when the range is empty.

## Left for the human

- **The first real run, which nobody has done yet.** In Chromium touch emulation at 1024×768:
  - open the menu on the last message of a scrolled channel, and on a reply at the thread
    panel's right edge, and check each menu shows in full;
  - check that a touch which starts a scroll closes the menu.

  On desktop, wheel-scroll "⋯" out of the list with its menu open, and judge #16.
- **Assumed decisions to read:** #10, #13, #14, #15, #16 and #17.
- **The integration layer** shows ⚪ not run in `docs/test-report.md`. This change touches none of
  its inputs, but rerun it before you rely on the report.
- **`tabIndex={-1}` on the list scroller and the thread panel** means a mouse press on their
  blank space focuses them. Check during the first run that no focus ring appears there.

## Checked and sound

- Round 1's *Checked and sound* still holds, since no code has changed since then.
- The new doc 06 bullet matches the code on all three paths it names.
