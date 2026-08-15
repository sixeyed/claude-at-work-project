# Slice 7 — Record the decisions

## Context

[`02-messaging-core-delivery-plan.md`](./02-messaging-core-delivery-plan.md) restructures the
messaging build into seven vertical slices, and Slice 7 is the last one. So this plan does two
things: it **validates the delivery plan's Slice 7 paragraph against the design docs and the
shipped repo** and closes the gaps found, and it **specifies Slice 7** in enough detail to build
from.

Slice 7 writes no code. It is the slice that stops the register, the design docs and the READMEs
drifting away from six slices of shipped behaviour — and the reason CLAUDE.md insists a decision is
recorded *in the slice that makes it* is that a sweep at the end is where drift gets discovered,
not where it gets prevented. Most of the recording therefore already happened: D24, D26 and D27
landed with Slice 1, and D8d lands with Slice 4 ([ruling 9](./04-slice-contracts.md)). **Re-recording
any of those here is a mistake, not thoroughness.**

**Demo, for a slice with no UI:** afterwards a reader who has never seen the repo can open the root
`README.md`, follow it to a frontend README that does not exist today, and learn from the *design
docs* — not from a plan and not from a service README — which messaging endpoints exist, which are
deliberately unbuilt, why there is no `jobs:index` producer, and which register rows are still open.
Today three of those answers are only in `src/services/messaging/README.md`, one is in no file at
all, and one is contradicted by the doc that wins the tie-break.

**Slice 7 runs last, after Slices 2–6 are built**, because its delivery-plan amendment is assembled
by reading those slices' "Gaps closed" sections. Validation found **eight gaps**, three of which
raise a **Contract question** because they land on documents [`04-slice-contracts.md`](./04-slice-contracts.md)
ruling 9 assigns to nobody.

---

## Gaps closed

### 1. The delivery plan's Slice 7 paragraph is mostly other slices' work

The delivery plan's `## Slice 7` lists five items. Ruling 9 reassigned two of them and Slice 1
shipped a third:

| Delivery plan says Slice 7 does | Actually |
|---|---|
| The **D8d ADR** in `docs/adr/` | **S4** — ruling 9. Decision 1 of the delivery plan still says "recorded in the D8d ADR in Slice 7" |
| Register **D8d → 🟢** | **S4** — ruling 9 |
| Reflect D8d into **doc 02 §9** | **S4** — ruling 9 ("strike the edit/delete-window line") |
| Reflect **D24 + styling into doc 06 §2** | **Already done in Slice 1.** Doc 06 §2 carries 🟢 rows for TanStack Query/Zustand, Tailwind v4 and pytest-bdd, and §9 has the strikethroughs |
| READMEs + `.env.example` | **S7** — but see gaps 2, 3 and 5; the work is not what the paragraph describes |

**The call: Slice 7's scope is the four things ruling 9 actually leaves it** — the register
*confirmation* pass (D16 🔴, D28 🔴, D8a/D8b/D8c 🟡), doc 02 §5's `jobs:index` note, the README
sweep, and the single dated amendment to the delivery plan. Everything else in that paragraph is
either done or belongs to Slice 4. **S7 verifies Slice 4's D8d work landed; it does not redo it.**

### 2. `src/frontend/README.md` does not exist — the plan says "README updates"

Ruling 9's last rows give S7 "READMEs: root, `src/frontend`, `src/services/messaging`", and the
delivery plan says "README updates: root, `src/frontend`, `src/services/messaging`". Two of those
three files exist. `src/frontend/` holds `index.html`, `package.json`, `vite.config.ts`,
`tsconfig.json`, `openapi/` and `src/` — and no README. The strategy plan
([`01-messaging-core-strategy-plan.md`](./01-messaging-core-strategy-plan.md) Phase 6) hedges it as
"`src/frontend/README` **material**", which reads like it noticed.

The root `README.md` compounds it. Its component table (line 54 onward) marks **Messaging** and
**Frontend SPA** as *scaffold* — but `src/services/messaging/README.md` has existed since Slice 1
and is linked from the "Running it locally" section of that same file, sixty lines below the table
that says it isn't there.

**The call: S7 creates `src/frontend/README.md` and repairs the table.** After the sweep, *scaffold*
means Canvas, Asset and Worker, and nothing else. Specified in work package D.

### 3. The root README's decision and current-state paragraphs are already stale

This is stale **before this slice starts**, not because of it. Root `README.md`:

- "Two register decisions were settled on 2026-07-28" — three more were settled 2026-08-15 (D24,
  D26, D27), with ADRs in `docs/adr/`, and D8d makes a fourth in Slice 4. A reader who trusts that
  sentence concludes the 2026-08-15 ADRs are undocumented decisions.
- "**Messaging has channels** … messages, threads and the Socket.IO `/messaging` namespace are
  still to come" — true when Slice 1 shipped, false after Slice 6.
- The repository layout block names `docs/design/`, `docs/adr/`, `docs/platform/`, `src/`, `docker/`,
  `charts/` and `.claude/skills/`. It omits `tests/bdd/` — the suite the same README spends thirty
  lines explaining how to run — and `docs/plans/`.

**The call: the root README's "Current state" and settled-decisions paragraphs are rewritten from
the register, not from memory**, and the layout block gains the two missing directories. The
register is the source of truth for what is settled (its own header says so); the README must not
carry a second, hand-maintained list that can disagree with it.

### 4. The soft-delete exceptions live only in the docs that lose the tie-break

Conventions §3 states the rule flatly: *"Mutable user-facing resources use `deleted_at timestamptz
NULL`. Queries filter `deleted_at IS NULL` by default."* There are now **two** documented exceptions
to that, and neither is in Conventions:

- `channels` has no `deleted_at` and archives through `archived_at` — recorded in doc 02 §4 by
  Slice 1 (gap 5 of [`03-slice-01-implementation-plan.md`](./03-slice-01-implementation-plan.md)).
- `messages` history deliberately **returns** soft-deleted rows so a tombstone survives a reload —
  ruling 1, built in S3, given semantics in S4.

CLAUDE.md is explicit that where a per-service doc disagrees with Conventions, **Conventions wins**.
So both exceptions currently live in the document that loses. CLAUDE.md itself is half-right: its
soft-delete bullet carries the `channels` exception and states the rule as "filter the soft-delete
column" — which is precisely what the messages read path does not do.

**The call: Conventions §3's soft-delete bullet names both exceptions and points at doc 02 §4 and
§3.1.4 for each; CLAUDE.md's bullet gains the messages tombstone case.** Neither edit re-decides
anything — ruling 1 made the call and S3/S4 wrote it into doc 02. This makes the authoritative
document agree with it.

**Contract question:** ruling 9's matrix assigns no owner to `docs/design/00-platform-conventions.md`
or to `CLAUDE.md`, because it only ranges over docs 02, 06, 07, `docs/adr/`, the READMEs and
`.env.example`. **Recommendation: S7 owns both**, for sweep-shaped edits that record decisions
already made elsewhere. No other slice touches either file, so nothing is being taken from anyone;
a *new* rule in either would be a Contract question in its own right, and none is proposed here.

> **Granted by ruling 19, 2026-08-15**, for **Conventions §3** (the soft-delete bullet and its two
> exceptions) and for `CLAUDE.md`. One exception: **Conventions §6 and doc 02 §4.1 are S5's**, not
> this slice's. S5 found that Canvas and Messaging would otherwise share `AsyncRedisManager`'s
> default `channel="socketio"` on one R2 instance, and recommended S7 carry the correction; ruling
> 19 overturned that. It is a decision S5's code forces, and CLAUDE.md says a decision is recorded
> in the slice that makes it — a sweep would land it after both services are already running.

### 5. Doc 02 describes the `jobs:index` producer as behaviour, in three places

Ruling 9 gives S7 "02 §5 — why the `jobs:index` producer is deliberately absent". It is in more
than §5:

- **§1 Purpose** — "**Produces:** index jobs to `jobs:index` (R3) for Elasticsearch (consumed by
  Worker)."
- **§4.1 Redis usage** — "**R3:** `jobs:index` — one job per created/edited/deleted message for ES
  sync."
- **§5 Internal Design — Send Message**, step 4 — `XADD jobs:index` with the full document, carrying
  a 🟢 D25 note that makes it read like settled, shipped behaviour.

None of it is built, and nothing consumes it: the Worker is scaffold and search is out of scope
(delivery plan, "Out of scope throughout"). `src/services/messaging/README.md` says so under
"Deliberately absent"; the design doc does not, and the design doc is what a reader consults first.

**The call: §5 gains the note — the step stays as the eventual shape, marked not built, with the
reason.** That is the same treatment ruling 2 gives `ix_messages_thread` in §4: leave the DDL as the
eventual shape and state the omission. §1 and §4.1 each get a one-clause pointer to §5 rather than
their own copy of the argument. **The `version` column earns its place on optimistic-concurrency
merit alone (Conventions §3), so adding the producer later is purely additive** — that sentence is
the point of the note and must survive into the doc.

### 6. Nothing marks the endpoints doc 02 §3.1 lists and this scope never builds

Doc 02 §3.1's table has eighteen rows. Ruling 9 assigns ownership **per row** — to S2, S3 and S4 —
but only for the rows those slices build. After six slices these rows are still in the table with no
marking of any kind:

| Row | Why it is not built | Register |
|---|---|---|
| `GET /messages/{id}/thread` | single-level threading unbuilt; `thread_root_id` ships as a column, always `null` | D8a 🟡 |
| `POST`/`DELETE /messages/{id}/reactions*` | the `reactions` table is not created (ruling 2) | — |
| `POST /channels/{id}/read` | `last_read_id` shipped in `0001_channels`; nothing writes it | — |
| `GET /search/messages` | no Elasticsearch path at all; no `jobs:index` producer (gap 5) | D8c 🟡 |
| `POST /internal/messages/sweep` | retention values unset | D16 🔴 |

The equivalent list exists in `src/services/messaging/README.md` and in the delivery plan's "Out of
scope throughout" — neither of which is the design doc.

The SPA has the same shape of drift. Doc 06 §7 promises "queue outgoing chat sends while
disconnected", which S6 does not build; doc 06 §3's tree gives `/src/app` and `/src/components`,
neither of which exists (the SPA has `App.tsx` and `main.tsx` at the `src/` root and no shared
components folder yet).

**The call: doc 02 gains a new §3.1.5, "Not built in this scope", carrying the table above.** It is
additive — it touches no row S2, S3 or S4 owns, and it sits after the §3.1.4 ruling 1 gives S4. Doc
06 gets the same treatment in two sentences in §7, and §3's tree is corrected to the shipped one.

**Contract question:** ruling 9 assigns no owner to unbuilt §3.1 rows, to doc 06 §3, or to doc 06
§7. **Recommendation: S7 owns all three**, via the additive §3.1.5 and edits confined to doc 06 §3
and §7 — leaving doc 06 §5.2 entirely to S5 and S6, whose rulings 9 rows name it.

> **Granted by ruling 19, 2026-08-15, as recommended.** One boundary to hold: **doc 06 §8 is
> S6's** — it removes the client-side message-length pre-check, so it corrects the sentence that
> describes it. And the new §3.1.5 is additive by construction, sitting alongside S4's new §3.1.4
> without editing a row either owns.

### 7. The register's D16 and D8d rows wait on each other

`docs/design/07-open-decisions-register.md`:

- **D8d** — "Recommendation: Align with Worker retention (D16)"
- **D16** — "Recommendation: Set concrete numbers; coordinate with D8d"

Once S4 settles D8d that cycle is broken on one side only, and D16 is left recommending
coordination with a decision that is finished. Worse, D8d's answer *removes* the dependency: with no
time window and tombstones retained in history, nothing about edit/delete semantics constrains a
retention number, and nothing about a retention number changes edit/delete semantics.

The register's "Settled" bulletin at the top (its `**Settled 2026-08-15:**` lines) is maintained by
hand and is a second place the same fact lives. If S4 flips the D8d row and not the bulletin, they
disagree.

**The call, and it stops short of an answer:** **D16 stays 🔴** per ruling 10 — S7 picks no number,
writes no sweep endpoint and does not touch `RETENTION_MESSAGE_DAYS` in `.env.example`, which is
already commented as a placeholder. Its *Recommendation* text is rewritten to say the coupling to
D8d is discharged and what remains open is the value alone. **D28 stays 🔴** likewise, with a note
that six slices shipped light-palette-only and stored no per-user choice. **D8a/D8b/D8c stay 🟡**,
each gaining one clause recording what the build assumed against them (ruling 10's table is the
source). Statuses do not move.

**Contract question:** if S7 runs and the D8d row still reads 🔴 — S4 having missed it — S7 fixes
the *register row and the bulletin* but **does not author the ADR**. An ADR written by whoever
swept last, rather than by whoever made the call, is a worse artefact than a missing one.
**Recommendation: S7 reports it and stops for the D8d ADR specifically**, rather than absorbing it.

> **Granted by ruling 19, 2026-08-15, as recommended.** A sweep that quietly writes another
> slice's ADR hides that the slice did not finish, which is the opposite of what this slice is for.

### 8. A docs slice has no definition of done

The delivery plan's "How every slice runs" step 6 gives one set of exit criteria for all seven
slices: scenarios green, ruff clean, integration suite green, `npm run build` clean. Slice 7 changes
no `.py`, no `.tsx` and no `.feature`, so every one of those passes by construction and none of them
is evidence of anything.

**The call: for this slice they are a regression guard, not exit criteria**, and the real check is a
link check plus a set of greps that assert the docs and the repo agree — specified in Verification.
This is the only slice where a green test run proves nothing.

### Also corrected in the delivery plan

Recorded here and written into the delivery plan by work package E:

- **Decision 1** says the tombstone exception is "recorded in the D8d ADR in Slice 7". Ruling 9 moved
  it to **S4**.
- **Decision 2** lists `last_read_id` among the columns whose features arrive later, as though it
  were still to come. It **shipped in `0001_channels`** (ruling 2).
- The **Slice 5 and Slice 6 paragraphs** still say `features/chat`; the folder is `features/channels`
  (doc 06 §3, ruling 7, moved in Slice 1).
- The **Slice 7 paragraph** claims doc 06 §2 and the root README's BDD instructions as pending; both
  shipped in Slice 1.
- **`.env.example` needs nothing.** Verified against `docker-compose.yml`: the `messaging` block
  already passes `POSTGRES_DSN`, all three Redis URLs — including `REDIS_REALTIME_URL`, which S5
  needs — and `CORS_ALLOWED_ORIGINS`. No slice in this scope introduces a variable, which matches
  ruling 9's last row. The check stays in Verification as a grep, because "no change expected" is
  only worth saying if something proves it.

---

## How the slice runs

Unchanged from the delivery plan, with the parts that do not apply named rather than quietly
dropped:

- **Step 1 (Gherkin first) does not apply.** Ruling 6's table gives S7 no feature file, no step
  module and no page object — the row is three em-dashes. Every scenario in scope was written by
  S2–S6. **This is deliberate: there is no acceptance test for a paragraph in a README**, and adding
  one would mean a scenario that asserts on documentation rather than behaviour.
- **Step 3 (build outside-in) does not apply**, and there are no integration tests, because there is
  no code. Nothing in this slice can fail at runtime.
- **Step 5 (`data-testid` selectors) does not apply** — no selectors, no page objects.
- **Step 2's 🛑 gate does apply**, attached to a different artefact. Present the design-doc, register,
  Conventions and CLAUDE.md diffs — work packages A, B and C — and **stop and wait for explicit
  approval** before the README sweep and the delivery-plan amendment. Same reasoning as the scenario
  gate: the cheapest thing to change is the thing that governs everything after it, and a wrong call
  about what is settled propagates into three READMEs.
- **Step 4 still binds, in the negative.** If the sweep finds a `.feature` file that contradicts a
  design doc, **never edit the scenario** — the scenario is the accepted contract, so either the doc
  is wrong or it is a defect to raise against the slice that wrote it.
- **Step 7 applies in full.** Branch `feature/messaging-s7-decisions`. Per CLAUDE.md: create the
  branch, leave the tree dirty, **never commit**.
- **S7 runs last.** Work package E cannot be written until Slices 2–6 have plans with "Gaps closed"
  sections to read.
- **Ignore `docs/project/`** throughout — it is book-production material, not project input, and it
  is excluded from the link check in Verification for that reason.

---

## Work

### A. The register — `docs/design/07-open-decisions-register.md`

- `docs/design/07-open-decisions-register.md` — the **D8d row**: verify it reads 🟢 with a date and a
  link to S4's ADR. If it does not, fix the row and the bulletin and **escalate the missing ADR**
  (gap 7's Contract question) — do not write it here.
- `docs/design/07-open-decisions-register.md` — the **"Settled" bulletin** under *Resolve First*:
  add the dated line naming D8d if S4 did not, matching the shape of the existing
  `**Settled 2026-08-15:**` lines. One fact, one place — the bulletin points at the row, it does not
  restate the reasoning.
- `docs/design/07-open-decisions-register.md` — the **D16 row**: status **stays 🔴**. Rewrite its
  *Recommendation* to "Set concrete numbers. No longer blocked on D8d — that settled with no edit or
  delete window and tombstones retained in history, so retention and edit semantics are independent.
  Nothing in the messaging core depends on a value: `POST /internal/messages/sweep` is not built."
  Cite ruling 10.
- `docs/design/07-open-decisions-register.md` — the **D28 row**: status **stays 🔴**. Add one clause:
  the messaging slices shipped a light-only palette and stored no per-user choice anywhere, so the
  decision is still unforced. This is the row the SPA's whole styling posture rests on (doc 06 §2),
  so it must not read as forgotten.
- `docs/design/07-open-decisions-register.md` — the **D8a/D8b/D8c rows**: all **stay 🟡**, each
  gaining one clause of what the build assumed, from ruling 10's table — `thread_root_id` ships as a
  column and serializes as `null` with no thread API (D8a) · `kind='dm'` is rejected by
  `CREATABLE_KINDS` in `messaging/models.py` and no DM is created or listed (D8b) · no
  `/search/messages` and no `jobs:index` producer (D8c). A 🟡 row that records what was built against
  it is the difference between a default and an assumption nobody wrote down.
- `docs/design/07-open-decisions-register.md` — **D23 and D24 are not touched.** Slice 1 wrote both;
  re-recording is the mistake ruling 9 names.

### B. Design docs — `docs/design/`

- `docs/design/02-messaging-service.md` **§5** — add the "deliberately absent" note after step 4,
  keeping the step. Lift the argument from `src/services/messaging/README.md`'s *Deliberately absent*
  section so the two agree word for word on the reason: nothing consumes the stream, the Worker is
  unbuilt, and `version` earns its place on optimistic concurrency alone (Conventions §3), so adding
  the producer later is additive. This is the section ruling 9 names as S7's.
- `docs/design/02-messaging-service.md` **§1** ("Produces") and **§4.1** (the R3 bullet) — one
  parenthetical each, pointing at §5. Not a second copy of the reasoning; a reader who lands on
  either line must not conclude the stream is live.
- `docs/design/02-messaging-service.md` — **new §3.1.5, "Not built in this scope"**, carrying gap 6's
  table verbatim, placed after the §3.1.4 that ruling 1 gives S4. It edits **no row** of the §3.1
  endpoint table, because those rows are owned per-slice by ruling 9.
- `docs/design/06-frontend-spa.md` **§7** — two sentences under *Offline / reconnect*: the outgoing
  send queue is not built; a send made while disconnected fails and surfaces its problem detail
  (S6's rollback path), and Yjs reconciliation is Canvas's, which is unbuilt. **§5.2 is untouched** —
  ruling 9 splits it between S5 and S6.
- `docs/design/06-frontend-spa.md` **§3** — correct the tree to the shipped one: no `/src/app` (the
  router and providers are `App.tsx` and `main.tsx` at the `src/` root). **`/src/components` does
  exist by the time this slice runs** — S2 creates it for `ProblemBanner.tsx` — so strike `/src/app`
  only. Check the tree before editing rather than trusting this bullet: it is the kind of claim that
  goes stale precisely because this slice runs last.
  `/features/channels` is already right, per ruling 7 and Slice 1.
- `docs/design/00-platform-conventions.md` **§3** — the soft-delete bullet names both exceptions and
  links each to where it is specified: `channels` archives through `archived_at` (doc 02 §4), and
  `messages` history returns tombstones with `body` redacted rather than filtering them (doc 02
  §3.1.4). **Conventions wins the tie-break against a per-service doc, so an exception recorded only
  in doc 02 is an exception the contract does not grant.** Gap 4's Contract question covers the
  ownership.
- `docs/design/02-messaging-service.md` **§9** is **S4's** (ruling 9) — verify the edit/delete-window
  line was struck; do not strike it here.

### C. Repository guidance — `CLAUDE.md`

- `CLAUDE.md` — the soft-delete bullet under *Conventions that are easy to get wrong*. It currently
  ends "The rule is 'filter the soft-delete column', not 'filter a column called `deleted_at`'" —
  which the messages read path deliberately breaks. Add the second exception with its reason in one
  clause: **history returns tombstones, so `history_page` and `get` filter neither** (ruling 1, doc
  02 §3.1.4). CLAUDE.md overrides default behaviour for every future session in this repo, so a rule
  that is wrong here is more expensive than a rule that is wrong in a design doc.
- `CLAUDE.md` — the *Settled so far* line under *Open decisions*: add **D8d** in the existing
  `D8d <one clause>` shape. Leave the 🔴/🟡/🟢 legend and the D28 paragraph as they are — D28 is still
  open and the paragraph explaining why the SPA is light-only is still exactly right.
- `CLAUDE.md` — no other change. In particular the *Testing* and *Repo layout* sections were brought
  current by Slice 1 and are correct.

### D. READMEs

- `src/frontend/README.md` — **new file**, modelled on `src/services/messaging/README.md`, not on
  `src/services/auth/README.md` (247 lines is a service with an `api.http` walkthrough to explain;
  the SPA is not). Sections, in this order: what it is and its spec link (doc 06) · **What is built**
  (sign-in through Auth's PKCE flow, the workspace switcher, the chat shell, and whatever S2–S6
  shipped — read `src/frontend/src/features/channels/` at the time, do not copy this list) ·
  **Rules worth knowing before you change anything here**, which is where the value is:
  - TanStack Query owns *all* server state; Zustand (`src/stores/chat.ts`) owns client state only,
    and there is never a second copy of a channel or message list in it (D24 🟢, ruling 7).
  - Query keys lead with the workspace id, so a workspace switch reads a different cache entry
    rather than relying on a lifecycle hook someone can forget (`useChannels.ts`).
  - Messaging types are **generated** from `openapi/messaging.json` (D23) — `src/types/messaging.ts`
    is output and is never hand-edited. The two commands, from ruling 8.
  - Tailwind v4 via `@tailwindcss/vite`, **no config files** — the theme is `@theme` tokens in
    `src/index.css`. **Light palette only**, because D28 is 🔴 and there is nowhere to store a theme
    choice; components use tokens, never literal colours, which is what keeps a dark palette cheap
    later.
  - `data-testid` attributes exist for the BDD suite and are part of the contract — removing one
    breaks a scenario in `tests/bdd/`, not a unit test.
  - Run it with `npm run dev` for frontend work, but **never for the BDD suite** — StrictMode fires
    the session restore twice and spends the rotating refresh token twice.
  - `npm run typecheck && npm run build` is the gate; `tsconfig.json` is strict with
    `verbatimModuleSyntax` and `allowImportingTsExtensions`.
- `README.md` (root) — the component table: **Messaging** links to `src/services/messaging/README.md`
  and **Frontend SPA** to `src/frontend/README.md`; *scaffold* is left against Canvas, Asset and
  Worker only. Fixes the contradiction in gap 2.
- `README.md` (root) — **Current state**: rewrite from what the six slices shipped. Messaging is no
  longer "channels only"; the Socket.IO `/messaging` namespace is no longer "still to come". Keep the
  paragraph honest about what remains scaffold (Canvas, Asset, Worker) and about `collabhub-contracts`
  still being empty.
- `README.md` (root) — the settled-decisions paragraph: replace the "Two register decisions were
  settled on 2026-07-28" framing with a pointer to the register plus the 2026-08-15 batch (D24, D26,
  D27) and D8d. **The register is the list; the README points at it** — a second hand-maintained list
  is what produced this gap.
- `README.md` (root) — the layout block gains `tests/bdd/` and `docs/plans/`. The BDD suite already
  has thirty lines of instructions in the same file and no line in the map.
- `README.md` (root) — the *Acceptance tests* section is **correct as it stands** (Slice 1 wrote it,
  including the port table and the interlock explanation). Re-read it against `docker-compose.test.yml`
  and change nothing unless a port moved.
- `src/services/messaging/README.md` — **What is built**: replace "Channels: create and list" with the
  full surface after S2–S6, and delete the "Not yet: … Channel administration … is the next slice"
  paragraph, which will be wrong in every particular.
- `src/services/messaging/README.md` — a new rule under *Rules worth knowing*: **messages history
  returns tombstones** and therefore filters no soft-delete column, the one place in this service
  where Conventions §3's default does not apply (ruling 1, doc 02 §3.1.4). Alongside the existing
  `archived_at` rule, which stays.
- `src/services/messaging/README.md` — a short Socket.IO section: the `/messaging` namespace, R2 only
  and never R1 or R3 (ruling 5), the handshake token, and that `POST /channels/{id}/messages` stays
  alive as the REST fallback (ruling 7) so removing it is not a cleanup.
- `src/services/messaging/README.md` — *Deliberately absent*: the `jobs:index`, `attachments`, sweep
  and `reactions` entries are all still true and stay. Add `ix_messages_thread` (ruling 2 — the column
  ships, the index does not) so the omission is not read as a mistake later.
- `.env.example` — **no edit expected.** Confirmed against `docker-compose.yml`: the `messaging`
  block already passes every variable the service reads, `REDIS_REALTIME_URL` included. The check is
  a grep in Verification; if it finds a variable, the slice that introduced it owns the fix
  (ruling 9), not S7.

### E. The delivery-plan amendment — `docs/plans/ch06/02-messaging-core-delivery-plan.md`

- `docs/plans/ch06/02-messaging-core-delivery-plan.md` — **one dated amendment blockquote covering
  all six slices**, in the shape of the existing `> **Amended 2026-08-15, after Slice 1 shipped.**`
  block and placed directly after it. Ruling 9: **only S7 amends this file.** Assemble it by reading
  each of `05-`…`09-slice-0N-implementation-plan.md`'s "Gaps closed" section and taking the
  corrections that change what a *future reader of the delivery plan* would otherwise believe —
  not every gap each slice closed, which is what those plans are for.
- The five corrections already known, from "Also corrected in the delivery plan" above, go in
  regardless: the D8d ADR moving to Slice 4 · `last_read_id` already shipped in `0001` ·
  `features/chat` → `features/channels` in the Slice 5 and 6 paragraphs · the Slice 7 paragraph's
  doc 06 §2 and README items already shipped in Slice 1 · `.env.example` needing nothing.
- **Do not rewrite the slice paragraphs themselves.** The amendment blockquote is how this plan
  records history; editing the body would erase what the plan said when it was written, which is the
  thing the blockquote exists to preserve.
- `docs/plans/ch06/04-slice-contracts.md` is **not** amended. It is the frozen record of the rulings
  the slices were built against, and a ruling that turned out awkward is a finding for a slice plan,
  not an edit to the contract.

---

## Verification

```bash
uv run ruff check . && uv run ruff format --check .    # no Python changed — a guard, not a check
uv run pytest -m "not integration and not bdd"         # ditto: proves nothing was touched by accident

# Every relative markdown link in the docs and READMEs resolves. docs/project/ is excluded
# deliberately — it is book-production material and out of bounds (CLAUDE.md).
uv run --no-project python - <<'PY'
import pathlib, re, sys
skip = {"project", "node_modules", ".venv", "dist"}
files = [*pathlib.Path("docs").rglob("*.md"), pathlib.Path("README.md"),
         *pathlib.Path("src").rglob("README.md"), pathlib.Path("CLAUDE.md")]
bad = [f"{md}: {link}"
       for md in files if not skip & set(md.parts)
       for link in re.findall(r"\]\(([^)]+)\)", md.read_text())
       if not link.startswith(("http", "#", "mailto:"))
       and not (md.parent / link.split("#")[0]).exists()]
print("\n".join(bad) or "all relative links resolve"); sys.exit(1 if bad else 0)
PY

# No register row is 🔴 for something six slices were built on.
grep -n "D8d" docs/design/07-open-decisions-register.md    # 🟢, dated, linking S4's ADR
grep -n "🔴" docs/design/07-open-decisions-register.md      # names each open row; 15 today, 14 after D8d
grep -rl "D8d" docs/adr/                                   # S4's D8d ADR is present, by name
grep -n "Settled so far" -A 3 CLAUDE.md                    # names D8d

# The docs no longer describe unbuilt behaviour as built.
grep -n "jobs:index" docs/design/02-messaging-service.md   # §1, §4.1 and §5 each carry the note
grep -n "3.1.5" docs/design/02-messaging-service.md        # the "Not built in this scope" section
grep -n "scaffold" README.md                               # Canvas, Asset and Worker only
test -f src/frontend/README.md && echo "frontend README exists"

# .env.example is still the full contract: every variable Compose interpolates is in it.
grep -ohE '\$\{[A-Z0-9_]+' docker-compose.yml docker-compose.test.yml | tr -d '${' | sort -u |
  while read -r v; do grep -q "^$v=" .env.example || echo "missing from .env.example: $v"; done
```

One operational note, and it is the only one: `docker/frontend/Dockerfile` does `COPY src/frontend/
./`, so adding `src/frontend/README.md` invalidates that layer and the SPA image rebuilds once on the
next `docker compose up --build`. Nothing else in this slice reaches a container — no migration, no
image content change, no restart needed, and a running stack is unaffected.

**Manual demo:** open the repo the way a new reader does. From root `README.md`, follow the component
table to `src/frontend/README.md` — a file that did not exist before this slice — and to
`src/services/messaging/README.md`, and confirm neither says "scaffold" or "the next slice". Then
open `docs/design/02-messaging-service.md` and answer three questions **without opening a plan or a
service README**: which message endpoints exist (§3.1 plus the new §3.1.5), why nothing writes to
`jobs:index` (§5), and why a deleted message still comes back from history (§3.1.4, and now
Conventions §3). Finish in `docs/design/07-open-decisions-register.md` and confirm every 🔴 left is
something nothing in the messaging core was built on.

**Done:** the link check passes, every 🟡 row records what the build assumed against it and every remaining 🔴 is
something nothing in the messaging core was built on,
every "not yet" and "next slice" line in the three READMEs is gone, the delivery plan carries one
dated amendment covering Slices 2–6, ruff and the fast test path are clean — and the working tree is
left dirty on `feature/messaging-s7-decisions` for you to commit.
