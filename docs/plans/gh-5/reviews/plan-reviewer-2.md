# Plan review — gh-5, round 2: approved

All eight round-1 findings are fixed in the plan. I checked each fix against the installed TanStack
Query source, `testkit`, `session.ts` and the test tree, and every one holds. Nothing new reaches
major, so no critical or major finding is open.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. A rename's cache writes lose to a read already in flight (major) | Decisions 30a, 30b; held-read tests in both orders in `useProfile.test.ts` and `session.test.ts`; `auth.meBy` | **resolved**. Checked in the primary checkout's `query-core/build/modern`. `cancelQueries` defaults to `revert: true` and cancels synchronously inside `notifyManager.batch` (`queryClient.js:141-147`). `retryer.js:29-34` rejects once, so a late response is dropped. `query.js:267-273` reverts the state. `query.js:188` confirms the plan's claim that a refetch cancels only a query that has data. `refetchType: 'all'` reaches inactive queries (`queryClient.js:156-176`), which the plan backs by mounting a real `useWorkspaceMembers` so the query has a `queryFn`. 30b's counter fits `adopt()` (`session.ts:76-94`), which reads `api.me` and then `set()`s. Its test holds the switch's read while the session is still signed in, so `updateProfile` applies. The "read started after" test pins the guard's other side |
| 2. Dedupe renames a newer name that was never a duplicate (major) | Decision 17a reserves names first; newer-holder fixture added at unit and in the migration test | **resolved**. Traced it: reserved keys are {`sam`, `sam 2`}, so `"sam"` (t1) → `"sam 3"` and `"Sam 2"` is untouched. A build that suffixes by age fails it. The earlier `…skips_a_suffix…` test agrees with the rule |
| 3. `CreateChannelDialog.test.tsx` missing from the ripple (major) | Added to the file map and Task 3's ripple | **resolved**. A grep for `<ChatLayout` and `<App` in `*.test.tsx` finds exactly the four files the plan lists |
| 4. Migration tests can't create their database inside the running loop (major) | `db_at_0001`: a sync fixture scoped to each test function | **resolved**. `testkit/databases.py:36-49` is synchronous and takes an async `upgrade`. `auth/migrations.py:39`'s `upgrade_to_head` is async, so an async `upgrade_to(dsn, rev)` matches both uses |
| 5. `a_user` names must differ in key, not just case (minor) | Each name is built from the user's own id | resolved |
| 6. Unqualified `version` in the upsert (minor) | Qualified | resolved |
| 7. A second visit can prefill from the cached profile (minor) | `isFetchedAfterMount` gate; field-value assertions; failed-read test | resolved. `queryObserver.js:328` compares `dataUpdateCount` with the count at mount, so a profile cached on an earlier visit doesn't count as this visit's read |
| 8. Step phrase departs from the vocabulary (minor) | Bare form through `parsers.re`, in the new module only (Decision 33) | resolved. The only existing binding is `test_message_steps.py:39` (`… written by Ada`), and modules don't share step definitions, so the two never meet |

## Findings

None.

## Left for later stages

- **Test-writer, `useProfile.test.ts` `a first directory load in flight is restarted`:** a query
  cancelled with no data reverts to `pending`/`idle` (`query.js:313-314`), and `setQueriesData`
  calls the updater with `undefined`. The test must let that path run as it really does. That way it
  fails a build whose updater dereferences `undefined`, or one that never refetches.
- **Code-writer:** `isFetchedAfterMount` also turns true on `setQueryData`, so `applyRename`'s write
  to `['me', id]` counts as a read for an open Settings page. That is harmless, since it is the
  server's own reply.
- **Decision 30b** keeps the session's whole profile (not only the name) over a read that began
  before the rename. That is fine while the rename is the only profile edit. A later profile field
  should revisit it.
- **Assumed decisions** the human should see at the end, carried over from round 1:
  - 14: length counted in code points.
  - 15–16: repairing and cutting an IdP name.
  - 17 and 17a: how the migration repairs stored names and which names it reserves.
  - 20: unknown stored keys left out of the response.
  - 24: Save's checks in the browser.
  - 25: return to the route after sign-in.
  - 26: Back to chat target.
  - 27: `/settings` inside the shell.
- Code pair: Decision 12's full case folding (`ß` = `SS`) is wider than `lower()`. The D46 ADR says
  so.

## Checked and sound

- Base commit `957371e` is the merge-base with `main`. The plan is 588 lines without *Review
  responses*. *Found while building* is still empty. No task commits. Every RED task (1–4) comes
  before every GREEN task (5–7).
- The round-2 edits broke nothing next to them. The Self-review, file map and Task 7 all name 30a,
  30b and 17a consistently. Task 8's doc 06 §5.2 entry cites 30a–b.
- Expected failures are unchanged. The new `session.test.ts` tests fail with `… is not a function`,
  which leaves the file's other tests running. The new `useProfile` tests fail with the file's
  existing load failure.
- All round-1 *Checked and sound* items still stand. None of them was in the diff
  `c5d7381..ed1d456`.
