# Plan review — gh-9, round 2: changes_requested

All seven round-1 findings are fixed, and each fix checks out against the issue and the repo.
One new major finding, from the fix to finding 3: the journey's new last step is a `Then` that
drives the app through eight screens. That breaks the suite's 🟢 rule *A `Then` never performs
an action* (vocabulary §16). Splitting it into a `When` and a `Then` settles it.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Rotating with a thread open and a draft: no decision row, no test | Decision 23 (**assumed**: both drafts; check 3 done as channel draft → thread → reply draft → rotate); a *Corrections* entry for check 3; two crossing rows, one each way, holding both textareas | **resolved.** Issue Acceptance 3 (`00-issue.md:99`) can't be done in its stated order at 390, so the correction is real. Both rows assert node identity and value for both drafts. The 390 → 844 → 390 row's red (☰ at the first 390 render) is the runtime's |
| 2. "and can be closed" on `/` has no test | New row: close with Close sidebar, then with ☰ and Escape; still on `/`, ☰ focused | **resolved.** A build whose arrival effect depends on `drawerOpen` reopens the drawer and fails this row |
| 3. The 360px checks rest on a hand run | `sideways_tour_at_360` over channel, thread, drawer (form filled, new-DM list open), DM, search, settings and sign-in. "Reached and used" left for the human. *Corrections* say check 4 has no sign-in | **resolved in substance.** The step's form is finding 1 below. Checked: `signed_out_context` (`conftest.py:364`), `open_settings` (`chat_page.py:151`), `search` with its resubmit loop (`:598-618`), `open_thread` (`:472`), the testids `create-channel-name`, `dm-new`, `dm-pick`, `search-box`, `sign-in` (`App.tsx:54`, outside the shell, so a signed-out `/sign-in` shows it) |
| 4. Wrong step in the expected red; sign-in leans on Decision 16 | The red is now at `Given Ada has created…`; Decision 16's role is spelled out under Task 3; `search`, `start_dm` and `open_settings` open the drawer first | **resolved** |
| 5. The last `Then` is local | Said under *What no test covers* | **resolved** |
| 6. Focus on two narrow-only paths | Decision 24 (**assumed**); asserted in the two Back rows and a crossing row with its neighbour (focus on the composer left alone) | **resolved.** Task 6 sends the focus through `ChannelView`'s close handler, so the browser's Back and the wide **Close thread** are untouched |
| 7. The conventions command won't run | Files from `git status --short`, by name | **resolved** |

## Findings

### 1. The journey's last step is a `Then` that performs actions — major
**Where:** Task 3 Gherkin, last line (`And at 360 wide, no screen Ada can reach scrolls
sideways`), and its step and page-object bullets · **Checked:**
`docs/plans/ch06/gherkin/00-scenario-vocabulary.md:350-366` (§16, 🟢), and the `search` docstring
at `chat_page.py:603-604`, which states the same rule ("no `Then` performs an action").

The step resizes the viewport, opens and closes a thread, fills the create-channel form, starts a
DM (which writes a DM to the server), searches, opens Settings and opens a signed-out page. All of
that runs inside a `Then`. The test-writer will build the Gherkin the plan dictates, and the
test-reviewer would have to send it back. **Settles it:** the tour as an act and the assertion as
a `Then` — for example `When Ada visits every screen at 360 wide` followed by `Then none of them
scrolls sideways`. The act records the tour's result and the `Then` asserts it is `{}`. Update the
*New* phrases bullet, the test-approach row and *What no test covers* to match. The step names are
yours to choose.

## Left for later stages

- **Decision 23 (assumed):** acceptance check 3 is performed as channel draft → open thread →
  reply draft → rotate. The acceptance-reviewer follows that order, not the issue's.
- **Decision 24 (assumed):** Back to channel focuses the channel composer, and crossing to narrow
  with focus in the sidebar focuses ☰. The issue doesn't require either.
- **Sign-in at 360** is not in the issue's acceptance check 4. The plan's *Corrections* ask the
  acceptance-reviewer to add it.
- The 360 tour starts a DM with Grace as a side effect. This is harmless in a scenario that
  truncates messaging, but the code pair should know the tour writes to the server.
- Carried from round 1: Decisions 13, 16, 17 and 20 (assumed) stand as recorded.

## Checked and sound

- Every round-1 fix is present in the plan text (diff `fed0cf7..db84b83`), and nothing else
  changed beyond what follows from those fixes.
- The new rows' expected reds are role-query failures in tests that run, not load failures.
- Both new guards prove their positive: "stays closed" reopens the drawer with ☰ between the two
  closes, and the focus-crossing row has its "focus elsewhere is left alone" neighbour.
- Without *Review responses* the plan is about 517 lines, inside 250–600. No GREEN task touches a
  test file. *Found while building* is empty. Nothing is built on a 🔴.
