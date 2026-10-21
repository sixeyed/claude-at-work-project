# gh-5 — acceptance proof: accepted

## Summary
- A new **Settings** page (`/settings`, reached by clicking your name in the sidebar) lets a signed-in user rename themselves; Ada's sidebar and her own message author show the new name at once, and Grace sees it on Ada's message after a reload.
- Display names are **unique across CollabHub, ignoring case**: Alan trying "GRACE" reads "That name is already taken." and keeps his name. The 409 body names no user and no workspace.
- The same page holds the first per-user preference, a **clock** (Automatic / 12-hour / 24-hour), stored by Auth: Grace's message time turns from `2:34 PM` style to `14:34`, and survives a reload.
- On this preview Grace's first sign-in was provisioned as "grace 2" because Alan had taken "GRACE" first (see *For the human*) — the first-sign-in suffix rule working, by accident, on the running app.

## Try it
- On GitHub, the PR's own preview: its origin is in the preview comment on the PR, and it stays up until the PR is approved or closed. Sign in as ada@collabhub.dev (grace@collabhub.dev too) with the preview password, which goes to the delivery's Slack thread — `collabhub` where Slack isn't set up
- Locally: `BRANCH=feature/gh-5 scripts/deploy.sh preview up`, then `preview url`; `preview down` when you're done

## Acceptance criteria
| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| 1 | Ada renames herself to `ada-<run id>`: sidebar and own messages show it at once; Grace, after a reload, sees it on Ada's message; Ada renamed back at the end | `test_ada_renames_herself_and_grace_sees_it` (fails on main: no `/settings`) | proven | [Ada](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-chromium-ada-sees-her-new-name-on-her-message.png), [Grace](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-chromium-grace-sees-the-new-name-on-adas-message.png) |
| 2 | Alan tries "GRACE": "That name is already taken.", name unchanged, 409 body names no user or workspace | `test_alan_cannot_take_graces_name` (fails on main: no page, and no uniqueness) | proven | [shot](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-alan-reads-that-name-is-already-taken.png) |
| 3 | Grace chooses 24-hour: a message sent after noon shows a 24-hour time; Automatic restored at the end | `test_grace_chooses_24_hour` — browser pinned to en-US and an afternoon zone, so only the preference turns `PM` into `14:34` | proven | [shot](../../../build/acceptance/feature/screenshots/test-grace-chooses-24-hour-chromium-grace-sees-a-24-hour-time-where-it-was-12-hour.png) |
| 4 | Req 3 — first sign-in suffixes a taken name (`X 2`, …) | Auth integration `test_display_names.py` (first-sign-in tests, concurrent case). Incidentally seen on the preview: Grace became "grace 2" | internal | — |
| 5 | Req 4 — migration trims, normalises and renames existing duplicates | Auth integration `test_name_migration.py`, unit `test_names.py` | internal | — |
| 6 | Req 6 — preferences GET/PATCH: merge, `null`, unknown key, `{}`, 404 for a deleted account | Auth integration `test_preferences.py` | internal | — |

## Preview
- Branch `feature/gh-5`, commit `09cea60`, tree clean when run (the runner commits every stage).
- Namespace `preview-feature-gh-5`; deploy outcome: up (`build/acceptance/preview-up.log`).
- Origin checks: the standard pack's routing and JWKS tests passed against the origin. The origin is a Cloudflare quick tunnel and is gone once the preview is taken down.

## Standard smoke pack
Passed, 6 of 6 (step 3), and 6 of 6 again beside the feature pack. No failures, no skips.

## Feature smoke pack
`build/acceptance/smoke/test_gh_5.py`, final run: **3 passed**, alongside the 6 standard tests (9 passed in 34 s).
- **`test_ada_renames_herself_and_grace_sees_it`** — Ada creates a channel and a message, renames herself on Settings, and the sidebar and the message author show `ada-<run id>`; Grace opens the channel in her own context, reloads, and the author reads the new name. Ada is renamed back in a `finally`. Passed.
- **`test_alan_cannot_take_graces_name`** — Alan saves "GRACE"; the PATCH answers 409, the body contains neither "grace" nor the workspace name, the field shows "That name is already taken.", no "Saved" appears, and a reload still shows his own name. Passed. Needs Grace to have signed in first (the test makes sure).
- **`test_grace_chooses_24_hour`** — en-US browser in a fixed-offset afternoon zone. Automatic shows `h:mm PM`; choosing 24-hour shows `14:34`; after a reload it is still 24-hour; Automatic is restored. Passed.

An earlier, unsuccessful run of this pack is not a result: Alan's test ran before Grace had ever signed in, so "GRACE" was free and his rename succeeded (see below), and the shared Ada fixture timed out once waiting for `workspace-name` during that run. The ordering was my test's fault and is fixed; the one-off Ada sign-in timeout did not recur in the final run or the probes, and is unexplained.

## Screenshots
**1a. Ada's own tab after renaming:** sidebar shows `ada-smoke-20261021-093416`, and so does the author of her message.

![Ada sees her new name](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-chromium-ada-sees-her-new-name-on-her-message.png)

**1b. Grace after a reload:** Ada's message is authored by the new name.

![Grace sees the new name](../../../build/acceptance/feature/screenshots/test-ada-renames-herself-and-grace-sees-it-chromium-grace-sees-the-new-name-on-adas-message.png)

**2. Alan trying "GRACE":** the field error "That name is already taken."

![Alan is refused](../../../build/acceptance/feature/screenshots/test-alan-cannot-take-graces-name-chromium-alan-reads-that-name-is-already-taken.png)

**3. Grace on 24-hour:** her message shows `14:34`, not `2:34 PM`.

![24-hour time](../../../build/acceptance/feature/screenshots/test-grace-chooses-24-hour-chromium-grace-sees-a-24-hour-time-where-it-was-12-hour.png)

## For the human
**Found on the preview**
- **The preview's state is order-dependent for the issue's own acceptance check.** The issue says Grace's name is never changed and "none needs a fresh preview", but on a fresh preview "GRACE" is only taken once Grace has signed in. My first run had Alan sign in first and rename himself to "GRACE" (200 — correct, it was free); Grace then signed in and was provisioned as **"grace 2"**, with workspace "grace 2's Workspace". I repaired both by hand-renaming Alan to "alan" and Grace to "grace" through the UI. Grace's workspace still reads **"grace 2's Workspace"** — by design a rename never renames a workspace. A person trying the preview should have Grace sign in first.
- Smoke channels (`smoke-…-rename`, `-clock`, `-chat`, `-files`) are left on the preview, as with the standard pack.
- A rough edge in screenshot 2: Save stays enabled after a 409 (it becomes disabled only when the value is unchanged or invalid); editing the field clears the error.
- In 12-hour mode with the 2-digit hour option, times can print with a leading zero (`09:34 AM`) — Automatic follows the browser's locale, as before.

**Assumed decisions** (plan; the code builds each as written): 14–17a, 20, 24–27 — name length counted in code points; repair of unusable IdP names; cutting the base so a suffixed name fits 100 characters; the migration repairing stored names that fail the rules; unknown stored preference keys omitted from the response; Save disabled when unchanged or invalid; return to the starting route after sign-in (new — the SPA didn't do it); the "Back to chat" target; `/settings` inside the chat shell.

**Departures** (green report): `useSetClock` writes/re-reads only when no other save is queued; `UpdatePreferencesRequest` has its own config; `update_me` pre-checks and maps only `uq_users_display_name_key`; `PATCH {}` writes nothing; `takeReturnPath` revalidates; clock radios never disabled while loading. The green run took no literal pre-build baseline.

**Left for the human** (green report, code review): the plan's by-hand first run (now largely covered by this proof — the signed-out `/settings` → sign-in → `/settings` path, a 24-hour thread summary and search result were **not** exercised here); the `name` token claim stays stale ≤15 minutes; confusables are out of scope; migration `0002` is a **one-way data change** that renames existing duplicates — read before deploying.

**Code review findings, all minor and open** (code-reviewer-1): (1) the plan's *Found while building* says the `useSetClock` "alone" gate is pinned by two tests; mutant 7 survives, so it is not. (2) A failed background read of the profile on `/settings` replaces an open form and drops the typed edit (`SettingsPage.tsx:169-177`). (3) Register D28's question cell still says "no feature for them exists at all".

**Unpinned** (code review): `adopt()`'s same-user check (mutant 3); the clock "alone" gate (mutant 7); Save compared against the cached profile rather than the first value (mutant 9); `provision_user` re-raising on a same-email race (mutant P2); the `update_me` 409 mapping only for `uq_users_display_name_key`. Possibly flaky: `App.settings.test.tsx › returns to the remembered route from the callback, once` failed once under a mutant that cannot reach it.

**Not exercised on the preview:** the clock in a thread summary and a search result (only the message time was), and the first-sign-in suffix on purpose (it happened by accident, see above).

## The run
- 01 plan-writer done (14.1m, 111 turns, opus)
- 02 plan-reviewer changes_requested (0 critical, 4 major, 4 minor)
- 03 plan-writer done (answered all 8 findings)
- 04 plan-reviewer approved (round 2, no findings)
- 05 test-writer done (36 Auth integration + 22 Vitest red)
- 06 test-reviewer changes_requested (1 major)
- 07 test-writer done (fixed)
- 08 test-reviewer approved
- 09 code-writer done (Vitest 568, unit 1993, integration 627, e2e 25/25)
- 10 code-reviewer approved (3 minor findings left for the human)
- 11 acceptance-reviewer: this proof — accepted
