# Test Pyramid D — `scripts/test.sh e2e` and the first triage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project rules override those skills.** **Never commit or stage** — leave the worktree dirty
> (CLAUDE.md, "Working in this repo"). Where a skill says "commit", this plan says "leave
> uncommitted". No Gherkin is added or rewritten here, so D27's "Gherkin is approved before it's
> built" is not triggered: the triage only deletes scenarios.

**Goal:** The BDD suite is a layer `scripts/test.sh` runs — `scripts/test.sh e2e` brings the test
stack up, runs the journeys, tears it down and returns pytest's exit code — and the demote rows
whose replacements have already landed are deleted.

**Architecture:** A `layer_e2e` function in `scripts/test.sh` drives
`docker compose -f docker-compose.yml -f docker-compose.test.yml` with `up --build --wait`, runs
`pytest tests/bdd -m bdd`, and tears down from an `EXIT` trap that preserves the exit status. The
readiness gap `--wait` leaves (the frontend has no healthcheck) is closed **in the stack**, with a
Compose healthcheck matching the chart's `/` probe, not with a polling loop in the script.

**Tech Stack:** bash 3.2, Docker Compose v5.4 (`--wait`, `!override`), pytest-bdd, Playwright
(sync, Chromium), uv.

**Spec:** [01-test-pyramid-design.md](01-test-pyramid-design.md) row **D** and "Framework 4", as
handed off in [03-test-pyramid-handoff-e2e.md](03-test-pyramid-handoff-e2e.md).

**Worktree:** `/Users/elton/scm/manning/caw-test-pyramid-e2e`, branch `feature/test-pyramid-e2e`,
from `main` at `5c15626`.

**Baseline**, measured 2026-09-15 in this worktree: `uv run pytest --collect-only -q -m bdd` →
**43** collected (34 scenarios, outlines expanded).

## Global Constraints

- bash 3.2: no associative arrays, no `mapfile`, no `${var,,}`; empty arrays expand as
  `${arr[@]+"${arr[@]}"}`.
- Share `scripts/lib/common.sh` (`log`, `die`, `require_cmd`, `REPO_ROOT`).
- The no-argument default stays `lint unit integration`; `all` becomes `lint unit integration e2e`.
- The suite reaches only the test stack's ports: SPA 5183, Auth 8011, Messaging 8012, Dex 5566,
  Postgres 5442. That interlock stays.
- Teardown is `down`, never `down -v`. `KEEP_STACK=1` skips it.
- Selectors stay `data-testid`-only, in page objects; steps stay synchronous.
- A demoted scenario is deleted only in the change that confirms its replacement exists and passes.

## Decisions made in this plan (assumptions, for Elton's review)

Elton asked for the handoff to be carried through without stopping for questions, so these were
decided rather than asked:

1. **Frontend readiness is a Compose healthcheck**, not a poll loop. `wget --spider` against
   `http://127.0.0.1:8080/` inside the `nginx:1.30-alpine` container — `127.0.0.1` rather than
   `localhost`, because Nginx listens on IPv4 only and busybox `wget` may resolve `localhost` to
   `::1`. It probes `/`, which is exactly what the chart's liveness and readiness probes
   (`charts/collabhub/values.yaml`, `components.frontend.probes`) already probe, so the two mean
   the same thing. Recorded on the D32 register row.
2. **`garage` and `otel-collector` stay without healthchecks.** No scenario reaches either, and
   neither is a `depends_on: service_healthy` target of anything the suite touches.
3. **The test stack runs with `--scale elasticsearch=0 --scale worker=0`**, held in one array
   (`E2E_SCALE`) in `scripts/test.sh` with a comment saying to delete it when a search journey
   lands.
4. **`--wait-timeout 300`**, so a container that never turns healthy fails the run instead of
   hanging CI.
5. **pytest is pointed at `tests/bdd`** as well as `-m bdd`, so the e2e run does not collect all
   453 service tests to deselect them.
6. **Two demote rows are deleted now, on the evidence of integration tests already on `main`.**
   The handoff's protocol reads the replacement tables from the unit (`04-…`) and integration
   (`05-…`) plans, and neither plan exists on `main` yet. But two rows name **only** an
   integration test, no Vitest and no new unit function, and both tests are already in the tree.
   This plan confirms them itself — reads them, runs them green — and deletes those two
   scenarios in the same change. Every other demote row needs a Vitest test (plan C has not
   landed) or `check_deletable` (deferred to the backfill), so it stays.
7. **`channel_reads` is listed in the harness truncate**, as Messaging's integration conftest
   does, so a future table without a foreign key to `channels` is not silently missed.

## File structure

| File | Change |
|---|---|
| `scripts/test.sh` | header, argument `case`, `all`, `layer_e2e`, `e2e_down` |
| `docker-compose.yml` | healthcheck on `frontend` |
| `docker-compose.test.yml` | header comment points at the script |
| `tests/bdd/conftest.py` | stack hint names the script; `channel_reads` truncated |
| `tests/bdd/features/channels.feature` | delete "A rename is visible to everyone in the workspace" |
| `tests/bdd/features/realtime.feature` | delete "Grace does not receive messages for a channel she is not looking at" |
| `tests/bdd/steps/test_channel_steps.py` | delete the orphaned `Ada has renamed the channel to` step |
| `README.md` | "Acceptance tests" rewritten around the script |
| `CLAUDE.md` | "Testing" commands block |
| `docs/design/00-platform-conventions.md` | §11 names the script |
| `docs/design/07-open-decisions-register.md` | D32 note: e2e layer, frontend healthcheck |

---

### Task 1: the `e2e` layer and the frontend healthcheck

**Files:** Modify `scripts/test.sh`, `docker-compose.yml`, `docker-compose.test.yml`,
`tests/bdd/conftest.py`.

**Interfaces:**
- Produces: `scripts/test.sh e2e [-- pytest args]`; env `KEEP_STACK=1`; `all` includes `e2e`.

There is no bash test harness in this repo, so "red" for a script is running it (handoff,
"Red for a script"). The runs are Task 3.

- [ ] **Step 1: frontend healthcheck** — in `docker-compose.yml`, under `frontend:`:

```yaml
    healthcheck:
      # Nginx serving static files has no /health endpoint, so this probes `/`,
      # exactly as the chart's liveness and readiness probes do. 127.0.0.1, not
      # localhost: Nginx listens on IPv4 only, and busybox wget may try ::1.
      test: ["CMD", "wget", "-q", "--spider", "http://127.0.0.1:8080/"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 5s
```

- [ ] **Step 2: `layer_e2e`** — in `scripts/test.sh`, beside `layer_integration`:

```bash
# The test stack, not the development one: docker-compose.test.yml gives it its
# own project, volumes and ports, because the suite truncates tables.
E2E_COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml)
# No scenario touches search yet. Delete this line when a search journey lands —
# that journey needs both.
E2E_SCALE=(--scale elasticsearch=0 --scale worker=0)

e2e_down() {
    local status=$?
    trap - EXIT
    log "e2e: taking the test stack down (KEEP_STACK=1 leaves it up)"
    "${E2E_COMPOSE[@]}" down || log "e2e: teardown failed; check 'docker compose -p collabhub-test ps'"
    exit "$status"
}

layer_e2e() {
    require_cmd docker
    docker info >/dev/null 2>&1 || die "e2e tests need Docker, and the daemon is not reachable"
    [ -f .env ] || die "e2e tests need .env at the repo root, which the Compose files read: cp .env.example .env"

    if [ "${KEEP_STACK:-}" = 1 ]; then
        log "e2e: KEEP_STACK=1, the test stack stays up afterwards"
    else
        trap e2e_down EXIT
    fi

    log "e2e: bringing the test stack up"
    "${E2E_COMPOSE[@]}" up -d --build --wait --wait-timeout 300 "${E2E_SCALE[@]}"

    log "e2e: installing Chromium for Playwright"
    uv run playwright install chromium

    log "e2e tests"
    uv run pytest tests/bdd -m bdd ${pytest_args[@]+"${pytest_args[@]}"}
}
```

`e2e_down` captures `$?` first, clears the trap so it cannot re-enter, and re-`exit`s with the
captured status, so a failed `down` can neither mask a pytest failure nor turn a pass into one.

- [ ] **Step 3: argument parsing and header** — `lint | unit | integration | e2e`, `all` →
  `lint unit integration e2e`, the unknown-layer message lists `e2e`, the default is unchanged,
  and the header documents `e2e`, `KEEP_STACK` and `-- --headed`.
- [ ] **Step 4: records in the stack files** — the `docker-compose.test.yml` header and the
  `_UP` hint in `tests/bdd/conftest.py` name `KEEP_STACK=1 scripts/test.sh e2e` first and keep
  the raw Compose command as the what-it-does reference. Add `channel_reads` to
  `MESSAGING_TABLES`.
- [ ] **Step 5: lint** — `bash -n scripts/test.sh`, `shellcheck scripts/test.sh` if installed,
  `docker compose -f docker-compose.yml -f docker-compose.test.yml config --quiet`,
  `uv run ruff check tests/bdd`.

### Task 2: triage — the two rows whose replacements have landed

**Files:** Modify `tests/bdd/features/channels.feature`, `tests/bdd/features/realtime.feature`,
`tests/bdd/steps/test_channel_steps.py`.

- [ ] **Step 1: confirm the replacements exist and cover the behaviour.**
  - *A rename is visible to everyone in the workspace* →
    `src/services/messaging/tests/integration/test_channels.py::test_a_rename_is_what_the_next_read_returns`
    — Ada renames, Grace's next list read returns only the new name. Messaging emits no rename
    socket event, so the next read is the whole behaviour.
  - *Grace does not receive messages for a channel she is not looking at* →
    `src/services/messaging/tests/integration/test_realtime.py::test_a_client_in_another_room_receives_nothing`
    — Grace joined to `random` receives nothing when Ada posts to `general`. The scenario's
    tail, Grace opening `general` and seeing the message, is the history read that
    "Grace sees Ada's message after reloading" keeps proving.
- [ ] **Step 2: run them green:**

```bash
scripts/test.sh integration -- \
  "src/services/messaging/tests/integration/test_channels.py::test_a_rename_is_what_the_next_read_returns" \
  "src/services/messaging/tests/integration/test_realtime.py::test_a_client_in_another_room_receives_nothing"
```

Expected: `2 passed`.

- [ ] **Step 3: delete the two scenarios**, and the step only the rename one used —
  `ada_has_renamed` (`Ada has renamed the channel to "{name}"`) in `test_channel_steps.py`.
  `ChatPage.rename_channel` stays: "A channel admin renames a channel" still uses it. No other
  step or page-object method is orphaned: `Grace opens the "…" channel`,
  `Grace sees "…" in the channel`, `Grace does not see …` and `… appears in Ada's channel exactly
  once` all have other callers.
- [ ] **Step 4: collect** — `uv run pytest --collect-only -q -m bdd tests/bdd | tail -1`.
  Expected: **41** collected, from 43.

### Task 3: verification runs

- [ ] **Run 1, the whole layer:** `scripts/test.sh e2e; echo "exit=$?"`. Expected: the stack
  comes up healthy, **41 passed**, the stack comes down, `exit=0`, and
  `docker compose -p collabhub-test ps -q` prints nothing.
- [ ] **Run 2, a broken scenario:** temporarily change `ada_sees_workspace` in
  `test_channel_steps.py` to assert against `name + "x"`, run
  `scripts/test.sh e2e -- -k "signs_in"; echo "exit=$?"`. Expected: 1 failed, `exit=1`, the
  stack is still torn down. Revert the change.
- [ ] **Run 3, `KEEP_STACK`:** `KEEP_STACK=1 scripts/test.sh e2e -- -k "signs_in"`. Expected:
  1 passed, `docker compose -p collabhub-test ps` lists running containers. Then take it down by
  hand with the raw Compose `down`.
- [ ] **Run 4, the default is unchanged:** `scripts/test.sh --help` shows `e2e`; a bogus layer
  prints the new message.

### Task 4: records

- [ ] **README "Acceptance tests":** lead with `scripts/test.sh e2e`, `KEEP_STACK=1` and
  `-- --headed`; keep the ports table, the interlock, `down` vs `down -v`, "not `npm run dev`",
  and the manual Compose commands as the reference. Fix the "The `bdd` suite is not part of it"
  sentence above.
- [ ] **CLAUDE.md "Testing":** add `scripts/test.sh e2e` to the commands block and replace the
  manual `up` / `pytest` lines.
- [ ] **Conventions §11:** the acceptance suite runs through `scripts/test.sh e2e`, which brings
  the throwaway stack up and down.
- [ ] **Register D32:** note that `scripts/test.sh e2e` is the e2e layer, and the frontend
  healthcheck it needed.

## Verification results — 2026-09-15

Every task above was executed in the worktree; results below.

| Check | Result |
|---|---|
| `bash -n scripts/test.sh`, `docker compose … config --quiet`, `ruff check tests/bdd` | clean (shellcheck not installed) |
| `scripts/test.sh --help`; `scripts/test.sh bogus` | help shows `e2e` and `KEEP_STACK`; `unknown layer 'bogus' (expected lint, unit, integration, e2e or all)`, exit 1 |
| Replacement tests via `scripts/test.sh integration -- …` | **2 passed** |
| Collected, `-m bdd` | **43 → 41** |
| Run 1, `scripts/test.sh e2e` | frontend `Waiting` → `Healthy` before pytest; Elasticsearch and Worker not started; **41 passed in 59s**; stack removed; exit 0 |
| Run 2, broken `ada_sees_workspace`, `-- -k signs_in` | `1 failed, 40 deselected`; exit 1; 0 containers left. Break reverted |
| Run 3, `KEEP_STACK=1 … -- -k signs_in` | `1 passed`; exit 0; 12 containers left up, all healthcheck-bearing ones `healthy`; removed by hand with `down` |
| Harness hint with no stack | now leads with `KEEP_STACK=1 scripts/test.sh e2e` |
| `scripts/test.sh lint unit` | `passed: lint unit` — ruff, conventions, eslint, tsc, helm clean; 123 unit passed |

## BDD triage status

**First pass** (before the unit and integration branches merged): 43 → 41, deleting the two rows
whose only replacement was an integration test already on `main`.

**Second pass**, after merging `main` at `f50c582`, which carries plan 04's and plan 05-backfill's
`## BDD replacements` tables: every remaining demote row has both halves confirmed, so all of them
are deleted, with every step definition, page-object method and harness fixture
(`seed_history`) that nothing else used. **41 → 15.**

| Scenario | Status | Replacements (from plans 04 and 05) |
|---|---|---|
| A rename is visible to everyone in the workspace | deleted (pass 1) | integration `test_a_rename_is_what_the_next_read_returns` |
| Grace does not receive messages for a channel she is not looking at | deleted (pass 1) | integration `test_a_client_in_another_room_receives_nothing`, `test_leaving_a_room_stops_the_broadcasts`. The SPA half, which room it joins, is not in plan 04's table but is asserted by `src/frontend/src/lib/realtime/useChannelSocket.test.tsx` (`join_channel` with the opened channel's id) |
| Ada creates a public channel — rows `team-42`, `Design-Review` | deleted; `general` kept | Vitest `CreateChannelDialog` (all three rows) |
| A public channel name cannot be reused, whatever its case | deleted | Vitest `CreateChannelDialog`; integration `test_public_names_collide_regardless_of_case`, `test_a_rejected_duplicate_leaves_one_channel` |
| A channel name cannot be blank / has to be typeable / ≤ 80 | deleted | Vitest `CreateChannelDialog`; unit `test_channel_rules.py` |
| A channel admin renames a channel | deleted | Vitest `ChannelHeader`; integration `test_an_admin_renames_a_channel` |
| An admin archives a channel and it leaves the list | deleted | Vitest `ChannelList`, `ChannelHeader`; integration `test_an_admin_archives_a_channel_and_it_leaves_the_list` |
| A message shows its author and timestamp | deleted | Vitest `MessageItem` |
| A blank message is not sent / over 8000 rejected | deleted | Vitest `MessageComposer`; unit `test_message_body.py` |
| Scrolling up loads older messages | deleted | Vitest `MessageList`; integration `test_pagination.py` |
| Ada cannot edit Grace's message | deleted | Vitest `MessageItem`; unit `test_message_policy.py`; integration `test_a_non_author_cannot_edit` |
| A channel admin deletes another user's message | deleted | Vitest `MessageItem`; unit `test_message_policy.py`; integration `test_a_channel_admin_deletes_another_users_message` |
| A non-admin cannot delete someone else's message | deleted | Vitest `MessageItem`; unit `test_message_policy.py`; integration `test_a_non_admin_cannot_delete_someone_elses_message` |
| A member without admin rights is not offered the channel controls | deleted | Vitest `ChannelHeader` |
| A typing indicator appears and clears | deleted | Vitest `useTyping`, `TypingIndicator`, `MessageComposer`; integration `test_typing_reaches_the_room_but_not_the_sender` |
| A sent message appears immediately and is confirmed | deleted | Vitest `useMessages` › `useSendMessage`, `MessageComposer` |
| A rejected send is rolled back and the error is shown | deleted | Vitest `useMessages` › `useSendMessage`, `MessageComposer` |

**The 15 journeys kept:** channels — signs in and sees her workspace; creates a public channel
(`general`); a new public channel appears for another member; a private channel only she can see.
messages — sends and sees it; Grace sees it after reloading; edits her own with a marker; deletes
her own and the tombstone survives reload. permissions — admin adds a member; removing revokes the
view; a non-member's link is a 404. realtime — Grace sees it without reloading; edit live; delete
live; the stream recovers after a drop.

The features' narrative paragraphs still describe the demoted rules. They are prose, not
scenarios, and rewriting Gherkin needs Elton's approval, so they are left as they are.

Two blocked deletions in the second pass (the auto-mode classifier flagged them as test removal)
went ahead once Elton granted the permission.

**Verified after the second pass:** 15 collected; `scripts/test.sh lint unit` passes (ruff,
conventions, eslint, tsc, helm; 209 pytest, 97 Vitest); `scripts/test.sh e2e` passes 15 on most
runs and tears down.

### The live-delivery flake — two SPA races, both fixed

The live-delivery journeys failed intermittently: 3 of 11 runs on a kept stack, with *Ada's
delete propagates to Grace live* and *Grace sees Ada's message without reloading* each failing.
Grace's page showed "Live" and never showed the change. Both causes were real message-loss bugs
in `useChannelSocket.ts`, unchanged since ch06, so a user could hit them too. Elton approved
fixing them here, test-first, with each set of failing tests reviewed at red.

**1. "Connected" was not "in the room"** — commit `6541212`. The hook set `connected` and emitted
`join_channel` with no ack, and refetched the history alongside the emit. The server enters the
room only after its visibility check, so a broadcast in that window missed the reader, and the
page object's `data-status="connected"` wait did not cover it. The join now asks for the ack; on
`ok` the store records `joinedChannelId` (rendered as `data-joined-channel`, which the page
object's `wait_for_channel_joined` waits on) and only then refetches. 7 Vitest tests. Afterwards
the delete scenario stopped failing, but *Grace sees Ada's message without reloading* still
failed 2 of 25.

**2. A history fetch overwrote a message that arrived while it was in flight** — commit
`73ce3f9`. Traced by logging Grace's socket frames and history requests (a throwaway plugin in
the scratchpad, not in the repo). In a failing run the history `GET` started at 2.622s, before
the message existed; `message_received` landed at 2.684s; the `GET` resolved at 2.685s with zero
items and replaced the cache. On a first load the event was dropped outright, against an empty
entry. An event that arrives while that channel's history is fetching is now applied again once
the fetch succeeds. 3 Vitest tests. Doc 06 §5.2 records both rules; doc 02 §3.2.3 the join order.

**Verified after both fixes:**

| Run | Result |
|---|---|
| Realtime journeys (`without_reloading or propagates or recovers`), kept stack | **0 of 30** failed |
| `scripts/test.sh all`, run 1 | passed — 209 pytest unit, 107 Vitest, 315 integration, 15 e2e |
| `scripts/test.sh all`, run 2 | passed — same counts |
| `scripts/test.sh all`, run 3 | the first attempt was killed mid-integration when the host ran low on memory (the k3d cluster was also up); rerun after clearing its orphaned testcontainers: passed — same counts, no containers left behind |

**Workstream 3, missing journeys:** nothing to draft. As of `5c15626` the SPA renders neither
search nor unread counts (`grep -rniE 'search|unread' src/frontend/src` finds only
`URLSearchParams`/`useSearchParams`), so there is no journey to write yet.
