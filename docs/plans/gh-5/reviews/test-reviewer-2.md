# Test review — gh-5, round 2: approved

The one open finding (round 1, #1) is fixed exactly as proposed. The round-2 commit changes one test file by two lines, and nothing else outside the report and run state. No finding is open.

## Responses checked
| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. `keeps a later choice when an earlier save fails` passed an unconditional rollback (major) | Fixed: `await pause()` added between `waitFor(preferenceRequests() === 2)` and `expect(radio('Automatic'))` | **Resolved.** `SettingsPage.test.tsx:383-385` has the comment and the `pause()` before the assertions. `git show --stat HEAD` lists this as the only test change (2 insertions). |
| Left-for-later items (commit-time conflicts, `onSettled` rollback) | No test change; they concern the build | Accepted, still carried below |

## What ran
- `git show --stat HEAD`, plus a read of the test at lines 358-393. This confirms the fix and that no other test file changed.
- I did not rerun a sketch. In round 1 I ran this exact edit in a sketch: the unconditional-rollback build went red and the correct build stayed green. The change is the same line, and nothing else in the file moved.
- The file still fails to load at red (`./SettingsPage` is missing). That is right, because every test in it needs the module. The other round-1 results stand, since no other file changed.

## Findings
None.

## Left for later stages
- **Code-writer:** the Python integration tests were never run against a build. Build `update_me` so the unique-index conflict can surface at `commit()` as well as at flush. The race tests rely on the first-sign-in insert flushing inside `provision_user`.
- **Code-writer (minor):** the SettingsPage and useProfile tests assume rollback in `onError`. A build that rolls back in `onSettled` should also pass. If it doesn't, tell the test pair.
- **BDD (unverified):** the first real run is the e2e in Task 9.
- **Assumed decisions for the human:** 14–17a, 20, 24–27.

## Checked and sound
Everything in round 1's *Checked and sound* stands. In short:
- The reds are for the right reasons.
- Both halves of each boundary are tested.
- The issue's clauses are pinned.
- Existing assertions are untouched.
- The report matches the tree.
