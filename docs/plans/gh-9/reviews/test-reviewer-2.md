# Test review — gh-9, round 2: approved

The round-1 critical (five tests typing into or focusing a disabled composer) is fixed in the tests only, in the way round 1's sketch showed gives 42/42. The red is still real: 38 fail on the missing behaviour, 3 more by a load failure every one of them needs, 1 passes by design. Nothing else changed.

## Responses checked
| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Composers disabled; five tests unpassable | `ChannelView.narrow` `renderShell` sets `connectionStatus` `'connected'` (store reset by `setup.ts` after each test); `App.narrow` has a `connected()` helper on the fresh `chat` module, called in the draft row, acceptance check 3's order and the focus-crossing row; the draft row waits for the `Message #general` textbox first | **Resolved.** Read in `git diff HEAD~1`; it is the fix round 1 named, and the same one its sketch ran 42/42 on. The two `ChannelView.narrow` tests that asserted composer focus are covered by the `renderShell` line. |
| 2. Report overstated "as planned" | Report says no sketch-green run was seen by the writer and relies on the round-1 sketch | **Resolved**, honestly stated. |
| 3. Decision 17 key vs test | Noted for the code-writer: reset the member panel on crossing to wide, say so in *Found while building* | **Let go** — a code-stage note, the test stays right. |
| 4. Journey arrangement unrun | Noted | **Let go**; a first-e2e matter. |

## What ran
- `npm --prefix src/frontend test -- src/App.narrow.test.tsx src/features/channels/ChannelView.narrow.test.tsx src/lib/layout/useNarrow.test.ts`: 38 failed in the two files that load (first lines are the missing ☰ / dialog / `Back to channel` / `Members`); `useNarrow.test.ts` fails to load (`./useNarrow` not found). The draft row now fails further on, as the report says.
- `npm --prefix src/frontend run typecheck`: one error, `useNarrow.test.ts(13,27) TS2307 './useNarrow'` — as reported.
- `git diff HEAD~1` on the two test files: three added `connected()` calls plus the helper, and one `setConnectionStatus` line in `renderShell`. No assertion changed, removed or loosened.
- `git status --short`: clean.
- **No new sketch.** The round-1 correct and wrong-build sketches were run on exactly this fix, and nothing else in the tests changed since. The one new detail, the draft row's `findByRole('textbox', { name: 'Message #general' })` before `connected()`, only waits for a box that the round-1 sketch already found. This is **unverified by a fresh run**, stated plainly.

## Findings
None new.

## Left for later stages
- **Decision 17** (round 1, Finding 3): the code-writer resets the member panel on crossing to wide — `membersOpenFor` keyed on `narrow` alone reopens it on a return — and says so in *Found while building*.
- **Journey** (round 1, Finding 4): if `is_where_left` raises `the arrangement did not separate the readings` at the first e2e run, send it back to the test pair for more filler.
- A `display:none` build that loses the scroll position is caught only by the journey.
- Plan-reviewer-3's notes stand: the 360 tour writes to the server; acceptance check 3 is performed in Decision 23's order; Decision 24 is assumed.

## Checked and sound
- Every red is the behaviour missing; none for a typo, path or fixture fault.
- No existing test touched beyond round 1's `setup.ts`; no production code, config or docs written.
- Round 1's wrong-build sketches (ten drawer builds, three panel builds, two hook builds) all failed the tests meant to catch them, and the tests those cover are unchanged.
