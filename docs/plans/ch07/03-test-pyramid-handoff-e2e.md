# Test pyramid handoff — end-to-end layer

Handoff, 2026-09-15. This is for an agent taking over the **end-to-end layer** of CollabHub's test
pyramid, with no context from the session that designed it. Two sister handoffs cover the other
layers: [unit](03-test-pyramid-handoff-unit.md) and [integration](03-test-pyramid-handoff-integration.md).

You own three workstreams:

1. **`scripts/test.sh e2e`.** The design calls this "plan D". Make the BDD suite a layer the
   scripts run, so it is no longer a manual README step.
2. **Triage the suite down to key journeys.** Delete the scenarios that move to lower layers, but
   only once their replacements have landed.
3. **Missing journeys.** Search and unread counts have none. Draft scenarios for Elton's approval
   once the SPA has the features.

Workstream 1 can start as soon as plan A is in. Workstream 2 depends on the unit and integration
handoffs' replacement tables. Workstream 3 depends on features that don't exist yet.

---

## Before you start

### Read these

| Document | Why |
|---|---|
| `CLAUDE.md` | The working rules, including the Testing section on the BDD suite. It wins over this handoff if they ever disagree. |
| `docs/plans/ch07/01-test-pyramid-design.md` | **The approved design, and your authority.** Read "The three layers" and all of "Framework 4 — End-to-end: key journeys only". |
| `docs/adr/260815-pytest-bdd-and-playwright-for-acceptance-tests.md` | D27: why pytest-bdd + Playwright (sync), `data-testid` only, page objects, and the named fragilities. |
| `docs/adr/260914-scripts-as-the-build-test-deploy-entry-point.md` | Why `scripts/` is the entry point, and the "Gherkin suite is not included" line you are superseding. |
| `docs/adr/260915-a-test-pyramid-with-journeys-at-the-top.md`, register D32 | The pyramid decision, written in plan A's Task 10. |
| `README.md` "Acceptance tests" | Today's manual procedure, ports and safety interlock. You rewrite this. |
| `tests/bdd/conftest.py` | The harness. Its docstring explains the sign-in, isolation and event-loop choices. **Read it before changing anything.** |

Ignore `docs/project/`. It's book-production material.

### Check the foundation is there

```bash
uv run pytest --collect-only -q -m bdd | tail -1              # 43 collected (34 scenarios, outlines expanded)
grep -n 'layer_unit\|layer_integration' scripts/test.sh        # both functions present
grep -n -- '-m unit' scripts/test.sh                           # plan A's marker-by-directory landed
```

Plan A is merged to `main`, so branch from `main`. If any of these fail, the foundation isn't
what this handoff expects. **Stop and ask Elton.**

### Working rules that bite

These come from CLAUDE.md and are repeated here because they are easy to get wrong:

- **Branch and worktree:** create a new git worktree on a new feature branch before your first
  edit, and tell Elton the branch name and path.
- **Never commit or stage.**
- **Decisions:** a 🔴 decision in the register means stop and ask. New register IDs are reserved
  per handoff, so the three parallel branches don't collide: **D33** unit, **D34** integration,
  **D35** end-to-end.
- **Write your plan into the repo.** Use superpowers:writing-plans to write it at
  `docs/plans/ch07/06-test-pyramid-e2e-<topic>-implementation-plan.md` (prefix `06` is
  reserved for this handoff; unit has `04`, integration `05`), and get
  Elton's approval before executing it.
- **Gherkin is approved before it's built** (D27). A new or rewritten scenario is drafted, shown to
  Elton, and only then gets steps and page-object code.
- **The suite's own rules:**
  - Selectors are `data-testid` only, and they live in page objects. A step definition never
    contains one.
  - Everything is synchronous. `asyncio_mode = "auto"` would collect an `async def` step as an
    asyncio test, and Playwright's sync API can't run inside a loop.
  - Sign in once per user into a live browser context. **Never** reuse a saved `storage_state`:
    the refresh token rotates, and Auth's reuse detection revokes the whole chain.
  - Run against the **built frontend container** on the test stack, never `npm run dev`. StrictMode
    double-restores the session and signs the user out.
  - **The suite truncates the Messaging tables before every scenario.** It runs only against the
    throwaway stack from `docker-compose.test.yml`, and reaches only that stack's ports: SPA 5183,
    Auth 8011, Messaging 8012, Dex 5566, Postgres 5442. That is the safety interlock; keep it.
- **Scripts:**
  - bash 3.2 (macOS): no associative arrays, no `mapfile`, no `${var,,}`.
  - Share `scripts/lib/common.sh`: `log`, `die`, `require_cmd`, `REPO_ROOT`.
  - A step that exists only in a pipeline or only in the README is a bug.
- **Hooks:** an edit hook runs ruff and **blocks** on findings, so fix them. `from tests… import`
  is banned (TID251). The suite imports itself as `bdd.*`.

---

## What the end-to-end layer is (settled)

| | |
|---|---|
| **Proves** | a key user journey works through a real browser and the whole stack. Only this layer proves CORS, `VITE_` values baked into the bundle, a migration running on container start, the OIDC redirect chain through Dex, and two browsers live. |
| **Where** | `tests/bdd/`: `features/*.feature`, `steps/`, `pages/`. The `testkit` plugin leaves it alone, and its tests are marked `bdd` by `pytestmark` in each steps module. |
| **Never** | A scenario that only restates a field rule. That belongs to unit or integration. |
| **Run** | Today by hand (README). After workstream 1: `scripts/test.sh e2e`. |

---

## Workstream 1 — `scripts/test.sh e2e`

### Behaviour

- **The new layer:** `e2e` joins `lint`, `unit` and `integration`.
  - `all` becomes `lint unit integration e2e`.
  - The **no-argument default stays `lint unit integration`**, so the everyday run stays fast.
  - CI runs `all`.
  - Update the header comment, the `case` in the argument loop, and the "unknown layer" message.
- **`layer_e2e`:**
  1. `require_cmd docker`, and check the daemon the way `layer_integration` does.
  2. Require `.env` at the repo root. The Compose files interpolate from it, for example
     `DEX_CLIENT_SECRET`. If it's missing, `die` with the README's instruction:
     `cp .env.example .env`.
  3. Bring the test stack up:
     `docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait`.
     **`--wait` is not enough on its own.** The five services built from `docker/` use the
     `*http-healthcheck` anchor, and Postgres, Redis, Elasticsearch and Dex have healthchecks. But
     **`frontend`, `garage` and `otel-collector` have none**, so `--wait` treats "running" as ready
     for those. Either:
     - add a healthcheck to `frontend` in `docker-compose.yml`. The runtime is `nginx:1.30-alpine`
       on port 8080, and a gap a script finds gets fixed in the stack, not worked around. **Or**
     - poll `http://localhost:${BDD_FRONTEND_PORT:-5183}` with a bounded loop.

     Record which one you chose. The harness's `stack_ready` fixture already fails with an
     instruction if nothing answers, so this is about not racing it.
  4. Consider `--scale elasticsearch=0 --scale worker=0`. The README suggests it because no
     scenario touches either. It becomes wrong the moment a search journey exists (workstream 3),
     so write it so it's easy to remove.
  5. `uv run playwright install chromium`. It's idempotent and quick when the browser is already
     installed.
  6. Run `uv run pytest -m bdd ${pytest_args…}`, preserving pytest's exit code.
  7. Tear down on exit: `trap` a `docker compose … down` that runs whether pytest passed or
     failed, **unless `KEEP_STACK=1`**, which a developer iterating on steps will want.
     - Keep volumes (`down`, not `down -v`). The suite truncates per scenario anyway, and the
       README explains why.
     - bash 3.2 `trap` with `set -euo pipefail` needs care so the exit code survives teardown.
- **Pass-through arguments:** `scripts/test.sh e2e -- --headed -k channels` works, because
  anything after `--` goes to pytest, as it does for the other layers.

### Red for a script

There's no unit-test harness for bash here, so the evidence is running it:
- the stack comes up
- 43 tests collected and passing
- the stack comes down
- a deliberately broken scenario makes the script exit non-zero *and* still tear down
- `KEEP_STACK=1` leaves the stack up

Put those runs in the plan as its verification steps.

### Records

- **README:** rewrite "Acceptance tests" around `scripts/test.sh e2e`. Keep:
  - the ports table
  - the safety-interlock explanation
  - `--headed`
  - `KEEP_STACK`
  - "not `npm run dev`"
  - the manual Compose commands, as the what-the-script-does reference
- **CLAUDE.md "Testing":** add `scripts/test.sh e2e` to the commands block, and replace the manual
  `docker compose … up` / `uv run pytest tests/bdd -m bdd` lines.
- **`docs/design/00-platform-conventions.md` §11:** say the acceptance suite runs through
  `scripts/test.sh e2e`.
- **ADR:** ADR 260915 already says this supersedes ADR 260914's "the Gherkin suite is not
  included". Don't edit the old ADR. If your implementation departs from the design, for example a
  frontend healthcheck, add it to the register row or a short ADR.

---

## Workstream 2 — Triage to key journeys

**The protocol.** Delete a scenario **only in the same change that confirms its replacement has
landed and passes**. For every scenario marked *demote*:
- the unit handoff delivers a Vitest or pytest replacement table, and
- the integration handoff delivers a confirmation table.

Work from those two tables: the `## BDD replacements` sections of
`docs/plans/ch07/04-test-pyramid-unit-*` and `docs/plans/ch07/05-test-pyramid-integration-*` on
`main`. Pull `main` before each deletion, because the other branches land over time. If a row has no replacement, the scenario stays, and you say so.

When you delete a scenario:
- delete any **step definitions and page-object methods** nothing uses any more
- run the suite through `scripts/test.sh e2e`
- report the collected count before and after

The target is **about 16 scenarios, down from 34**. The design's table, with its one open row
resolved:

| Feature | Scenario | Verdict | Covered below by |
|---|---|---|---|
| channels | Ada signs in and sees her workspace | **keep** (OIDC, CORS, baked env) | — |
| channels | Ada creates a public channel and lands in it | **keep one example row** | the other outline rows → Vitest `CreateChannelDialog` |
| channels | A new public channel appears for another member | **keep** | — |
| channels | A public channel name cannot be reused, whatever its case | demote | integration `test_public_names_collide_regardless_of_case`; Vitest shows the problem |
| channels | A channel name cannot be blank / has to be one people can type / not longer than 80 | demote | unit `validate_name`; Vitest `CreateChannelDialog` |
| channels | A channel admin renames a channel | demote | integration `test_an_admin_renames_a_channel`; Vitest `ChannelHeader` |
| channels | A rename is visible to everyone in the workspace | **demote** (resolved) | integration `test_a_rename_is_what_the_next_read_returns`. Grace *opens* CollabHub after the rename, and Messaging emits no rename socket event, so the next read is the whole behaviour. |
| channels | An admin archives a channel and it leaves the list | demote | integration `test_an_admin_archives_a_channel_and_it_leaves_the_list`; Vitest `ChannelList` |
| channels | Ada creates a private channel and only she can see it | **keep** | — |
| messages | Ada sends a message and sees it in the channel | **keep** | — |
| messages | A message shows its author and timestamp | demote | Vitest `MessageItem` |
| messages | A blank message is not sent / over 8000 characters is rejected | demote | unit `validate_body`; Vitest `MessageComposer` |
| messages | Scrolling up loads older messages | demote | integration `test_pagination.py`; Vitest `MessageList` |
| messages | Grace sees Ada's message after reloading | **keep** | — |
| messages | Ada edits her own message and it shows an edited marker | **keep** | — |
| messages | Ada cannot edit Grace's message | demote | unit `check_editable`; Vitest `MessageItem` |
| messages | Ada deletes her own message and a tombstone remains after reload | **keep** | — |
| messages | A channel admin deletes another user's message / A non-admin cannot delete someone else's | demote | unit `check_deletable`; integration `test_messages.py` |
| permissions | A member without admin rights is not offered the channel controls | demote | Vitest `ChannelHeader` |
| permissions | An admin adds a member to a private channel and they can see it | **keep** | — |
| permissions | Removing a member revokes their view of the private channel | **keep** | — |
| permissions | A non-member cannot open a private channel by its URL | **keep** (the SPA's route to a 404) | — |
| realtime | Grace sees Ada's message without reloading | **keep** | — |
| realtime | Ada's edit propagates to Grace live / Ada's delete propagates to Grace live | **keep** | — |
| realtime | Grace does not receive messages for a channel she is not looking at | demote | integration `test_realtime.py` rooms |
| realtime | The stream recovers after the connection drops | **keep** | — |
| realtime | A typing indicator appears for Grace and clears when Ada stops | demote | integration `test_typing_reaches_the_room_but_not_the_sender`; Vitest `TypingIndicator` |
| realtime | A sent message appears immediately and is confirmed | demote | Vitest `useSendMessage` |
| realtime | A rejected send is rolled back and the error is shown | demote | Vitest `useSendMessage` |

**Merging kept scenarios into longer journey-shaped scenarios** is optional and comes later. It
rewrites Gherkin, so it needs Elton's approval first.

### Harness notes found during the handoff

- **`tests/bdd/conftest.py` resets the database between scenarios.** It truncates
  `MESSAGING_TABLES = "messages, channel_members, channels"` with
  `TRUNCATE … RESTART IDENTITY CASCADE`.
  - `channel_reads` (D31, migration `0003`) isn't listed, but it has a foreign key to
    `channels.id`, so `CASCADE` clears it.
  - Messaging's integration conftest lists it explicitly. Consider listing it here too, so the
    next table without a foreign key isn't silently missed.
- **`@pending` exists.** A hook turns the tag into a skip, and the pyproject explains it. Use it
  for scenarios approved ahead of their code.

---

## Workstream 3 — Missing journeys

- **Search.** `GET /search/messages` is built (ADR 260914), but **the SPA has no search UI yet**;
  a grep of `src/frontend/src` finds none. There's no journey to write until the UI exists. When it
  does, the test stack must run the Worker and Elasticsearch, so remove any `--scale … =0` from
  workstream 1.
- **Unread counts.** The API returns `lastReadId` and `unreadCount` on every `Channel` (D31), but
  **the SPA doesn't render them yet**. Same situation.

For each one, once the feature exists: draft the Gherkin, get Elton's approval, then write steps
and page objects with `data-testid` selectors, which the SPA work must add.

---

## Done when

- `scripts/test.sh e2e` brings the test stack up, runs the suite, tears it down, and returns
  pytest's exit code. It honours `KEEP_STACK=1` and pass-through args.
- `all` includes `e2e`, and the default doesn't.
- README, CLAUDE.md and Conventions §11 describe the script.
- Every *demote* row is either deleted with its replacement confirmed, or explicitly kept with a
  reason.
- The unused steps and page-object methods are gone.

## Not yours

- **The unit handoff owns these:** writing the Vitest and pytest replacements.
- **The integration handoff owns these:** confirming and writing the integration replacements, and
  all testcontainers work.
- **Out of scope:**
  - Playwright's TypeScript runner (rejected in ADR 260815)
  - visual regression and cross-browser testing
  - running the suite against k3d
- **Search and unread SPA features:** not yours. You wait for them.

## Coordinating with the other two handoffs

- **`scripts/test.sh`:** you add `layer_e2e`, changing the argument `case` and the `all` expansion.
  The unit handoff edits `layer_unit`. Both handoffs edit the script's header comment, so expect a
  small conflict there and resolve it by keeping both sets of changes.
- **`docker-compose.yml`:** if you add a frontend healthcheck, `scripts/deploy.sh` and the Helm
  chart are unaffected. The chart has its own probes. Check `charts/collabhub/templates/frontend/`
  anyway, and don't let the two drift in meaning.
- **CLAUDE.md "Testing" and `docs/design/00-platform-conventions.md` §11:** all three handoffs may
  edit these. Re-read both sections from `main` before editing, and expect to merge text.
- **Replacement tables:** you consume them. Don't delete ahead of them.
