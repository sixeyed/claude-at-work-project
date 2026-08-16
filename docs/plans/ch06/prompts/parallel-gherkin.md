# Prompt: write the Gherkin for Slices 2–6 in parallel

Paste the fenced block below into a **fresh Claude Code session at the repo root**. It writes
scenarios; it builds nothing. This is step 1 of every slice's plan — the `.feature` files that
stop at the 🛑 gate before any code exists — done for five slices at once instead of five times
over. See `02-messaging-core-delivery-plan.md` §"How every slice runs".

It runs seven subagents in three waves: three writers, then two more, then two reviewers. Expect
seven new files in `docs/plans/ch06/gherkin/` and four touched in `tests/bdd/features/`, all
uncommitted.

Slice 7 has no Gherkin — ruling 6's table gives it three em-dashes — so this is five slices, not
six.

---

``````markdown
You are coordinating the writing of the Gherkin scenarios for Slices 2 to 6 of the CollabHub
messaging build. Each of those slices has a finished implementation plan whose first step is
"write the `.feature` file, then stop". You are doing that first step for all five at once.

**You are the coordinator and you stay the coordinator.** You do not write a slice's scenarios.
Your context is for the vocabulary the five files share and for consolidating the drafts. Five
subagents write the Gherkin; two more review it.

## Read this first

Nothing below happens until you have read:

- `CLAUDE.md` — the repo rules, and the Testing section describing the `tests/bdd` suite.
- `docs/plans/ch06/02-messaging-core-delivery-plan.md` §"How every slice runs" — the seven-step
  protocol the 🛑 gate comes from.
- `docs/plans/ch06/04-slice-contracts.md` — the frozen cross-slice rulings. **Ruling 6, "BDD
  harness growth", is the one that governs this run**: it says which slice owns which feature
  file, and it is binding.
- The five slice plans, specifically each one's `## How the slice runs` (the scenario titles and
  the paragraph naming what deliberately stays at integration level) and its BDD work package,
  `### A.`:
  - `05-slice-02-implementation-plan.md` · `06-slice-03-implementation-plan.md`
  - `07-slice-04-implementation-plan.md` · `08-slice-05-implementation-plan.md`
  - `09-slice-06-implementation-plan.md`
- `tests/bdd/` in full — `features/channels.feature`, `steps/test_channel_steps.py`,
  `pages/chat_page.py`, `pages/sign_in_page.py`, `conftest.py`. This is the only Gherkin the repo
  has and it is the shape everything you commission must match.

**Ignore `docs/project/` entirely.** It is book-production material, not project input.

Three facts about the harness that shape the whole run:

1. **pytest-bdd only generates tests for a feature some module calls `scenarios()` on.**
   `tests/bdd/steps/test_channel_steps.py:26` does that for `channels.feature` and nothing else
   does it for anything. So a new `.feature` file arriving in `tests/bdd/features/` is inert
   until its slice writes a step module — but scenarios appended to `channels.feature` run
   immediately, and fail on missing step definitions.
2. **Every Gherkin tag becomes a pytest marker and has to be declared** in `pyproject.toml:69`.
   `bdd` and `smoke` are declared. Nothing else is, and this run does not add one.
3. **Ada and Grace are the only signed-in users.** Ruling 6 forbids a slice adding a
   session-scoped fixture that signs a third user in.

---

## What gets written

| File | Written by |
|---|---|
| `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` | You, in Phase 1 |
| `docs/plans/ch06/gherkin/s2-channels.feature` · `s2-permissions.feature` | Writer 2 |
| `docs/plans/ch06/gherkin/s3-messages.feature` | Writer 3 |
| `docs/plans/ch06/gherkin/s5-realtime.feature` | Writer 5 |
| `docs/plans/ch06/gherkin/s4-messages.feature` | Writer 4 |
| `docs/plans/ch06/gherkin/s6-realtime.feature` | Writer 6 |
| `tests/bdd/features/channels.feature` · `permissions.feature` · `messages.feature` · `realtime.feature` | You, in Phase 4 |

The staging folder is new. Nothing else in the repo changes — no `src/`, no `docs/design/`, no
`pyproject.toml`, no `conftest.py`, no `pages/`, no `steps/`.

---

## Phase 1 — freeze the vocabulary

Do this yourself, before dispatching anything. Write
`docs/plans/ch06/gherkin/00-scenario-vocabulary.md`.

Five writers working blind will invent five ways to say "Ada opens the channel", and the step
author downstream then has to reconcile them. This document is the answer. It is what
`04-slice-contracts.md` is for the code — a set of **rulings**, not a summary.

Rule on every item below.

1. **Personas.** Ada and Grace, and no one else. Ada administers what she creates; Grace is the
   other member of the same workspace. A scenario that seems to need a third person is a
   **Contract question**, not a local decision (ruling 6).
2. **Step phrases the suite already has**, quoted verbatim from `steps/test_channel_steps.py`
   so a writer can reuse rather than paraphrase — `Given Ada is signed in` ·
   `Given Ada has created a public channel named "{name}"` · `When Grace opens CollabHub` ·
   the `Then Ada is told …` complaint idiom. Note the loose matching behind it (`_COMPLAINTS`,
   `test_channel_steps.py:29`): a scenario says *which rule* was reported, never the exact copy,
   so wording can change without a test failing. A writer either reuses a phrase exactly or
   introduces a new one deliberately and lists it in its return.
3. **One `Background` per file and one narrative paragraph per file**, both written by the slice
   that *creates* the file. An extending slice contributes scenarios only — never a second
   `Background`, never a second paragraph. `channels.feature` already has both.
4. **Tags.** `@bdd` on the `Feature` line, nothing else. `@smoke` stays on the one scenario that
   carries it. A new tag needs a marker declared in `pyproject.toml:69`, which is out of scope
   here — a writer that wants one raises it as a Contract question.
5. **`Scenario Outline` with `Examples`** wherever the rule under test is a table of cases,
   following the name-validation outline at `channels.feature:55`. A rule with one case is a
   plain `Scenario`.
6. **Browser-observable only.** A step says what a person did or what they saw. No step names an
   endpoint, a table, a column, a socket event or a `data-testid`. If the only way to observe
   something is a database row or a network trace, it is not a scenario.
7. **What never becomes a scenario.** Collect the "staying at integration level" paragraph from
   each of the five plans into one list, so no writer relitigates it: 409 version conflicts
   (ruling 3) · 403-vs-404 and cross-workspace tenancy · the exact problem `type` and `errors`
   map of a rejection · cursor mechanics and `nextCursor` · socket handshake failures and the
   `access_token` query fallback · the ack timeout. Each plan is the authority for its own
   slice; you are collecting, not deciding.
8. **Waits are events, not sleeps.** No step says "waits five seconds". A scenario asserts on a
   state the app reaches; how long the page object waits is the page object's business.
9. **Ordering is explicit where it matters.** Until Slice 5 there is no real-time delivery, so a
   cross-user assertion has to put Grace's load *after* Ada's change or it asserts on a cached
   list. S2's plan says this; the rule holds for S3 and S4 too.

Write it in the house style of the other ch06 documents: sentence-case title, `## Context` first,
`---` between sections, ~100-column wrap, `·` as an inline separator, 🔴🟡🟢 used the way the
register uses them.

---

## Phase 2 — wave one, three writers in parallel

**Issue all three Agent calls in a single message.** One per message runs them sequentially and
wastes the entire point.

Writers 2, 3 and 5 — the slices that *create* their feature files. Each writes its own file and
no two write the same one; that disjointness is what makes the fan-out safe without worktrees.

Use this prompt for each, substituting the placeholders:

````
You are writing the Gherkin scenarios for ONE slice of the CollabHub messaging build: Slice
{{N}}, "{{TITLE}}".

Write them to `docs/plans/ch06/gherkin/{{OUTPUT_PATH}}` and to no other file. Everything else in
the repository is read-only to you.

## What this is

Every slice plan's first step is "write the `.feature` file, stop, and wait for approval before
any code exists". You are doing that step. The scenarios are the contract for the slice and the
cheapest thing in it to change, which is why they get written and reviewed before anything else.

You are writing a **staged draft**. The coordinator consolidates it into
`tests/bdd/features/{{TARGET}}` afterwards.

## Read

- `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` — **the frozen shared vocabulary.
  Binding.** Where it rules on something, follow it; do not re-decide it.
- `docs/plans/ch06/{{PLAN}}` — your slice's plan. `## How the slice runs` has your scenario
  titles and the paragraph naming what deliberately stays at integration level. `### A.` has the
  page-object methods your scenarios imply — read it to know what the harness will be able to
  do, not to describe it.
- `docs/plans/ch06/04-slice-contracts.md` ruling 6 — which feature file is yours.
- `tests/bdd/features/channels.feature` — **the shape to match**, for register and rhythm as
  much as for content.
- `tests/bdd/steps/test_channel_steps.py` and `tests/bdd/pages/chat_page.py` — what the suite
  can already say and already do.

**Ignore `docs/project/`.** Read what your slice needs; do not sweep the repo.

## What to write

A single `.feature` file:

- `@bdd` on the `Feature` line, then `Feature: {{FEATURE_NAME}}`.
- **A narrative paragraph** — indented under the `Feature` line, the way `channels.feature`
  opens. It states the rules the file is about in the language of the people who use the
  product, not the schema. This is the part a non-engineer reads to check the behaviour is what
  they wanted, so it is worth real effort.
- `Background:` if every scenario needs the same setup — `Given Ada is signed in`, as
  `channels.feature` has.
- Your slice's scenarios, in the order the plan lists them.

## Rules

- **Write Gherkin and nothing else.** No step definitions, no page objects, no service code, no
  `conftest.py` change, no `pyproject.toml` edit.
- **The scenario titles are the plan's, not yours.** Flesh each one into Given/When/Then. Do not
  add one the plan does not list; do not drop one it does. If a title cannot be written honestly
  through a browser, write your best attempt and **say so in your return** — never quietly
  reshape it into something easier.
- **Reuse the existing step phrases exactly** where one fits. Every phrase you introduce that
  the suite does not already have goes in your return.
- **Nothing the plan sent to integration level** appears as a scenario.
- **No `data-testid`, no endpoint, no socket event, no column name** in any step.
- **Ada and Grace only.**
- Never run `git add`, `git commit`, or open a PR. Do not spawn subagents.

## Return

Fifteen lines maximum, as data for the coordinator, not prose for a human:

- the scenario titles you wrote, one line each;
- step phrases you introduced that the suite does not already have;
- any title you could not write honestly, and why;
- **Contract question:** items, with your recommendation.
````

Substitutions:

| `{{N}}` | `{{TITLE}}` | `{{PLAN}}` | `{{OUTPUT_PATH}}` | `{{TARGET}}` | `{{FEATURE_NAME}}` |
|---|---|---|---|---|---|
| 2 | Channel administration and membership | `05-slice-02-implementation-plan.md` | `s2-channels.feature` and `s2-permissions.feature` | `channels.feature` and `permissions.feature` | see below |
| 3 | Messages: send and read history | `06-slice-03-implementation-plan.md` | `s3-messages.feature` | `messages.feature` | Messages |
| 5 | Real-time delivery (broadcast only) | `08-slice-05-implementation-plan.md` | `s5-realtime.feature` | `realtime.feature` | Real-time delivery |

Slice 2 needs an extra paragraph in its dispatch, because it is the one writer with two files:

> You write **two** files. `s2-channels.feature` holds only the four scenarios that extend the
> existing `channels.feature` — give it a `Feature: Channels` line so it parses on its own and a
> `# --- appended by Slice 2 ---` comment above the scenarios, but **no narrative paragraph and
> no `Background`**: `channels.feature` already has both and the coordinator strips your header
> at consolidation. `s2-permissions.feature` is a whole new file, `Feature: Permissions`, with
> its own narrative paragraph stating the rule it is about — a public channel is the workspace's,
> a private channel is its members', and administering either takes a channel admin.

---

## Phase 3 — wave two, two writers in parallel

**Both Agent calls in one message.** Writers 4 and 6 extend files that wave one has just written,
so they run second — S4 needs S3's wording and S6 needs S5's, or the suite ends up with two
spellings of one step.

Same prompt as Phase 2, with this replacing the "What to write" section:

> You are **extending** a file another slice created. Read
> `docs/plans/ch06/gherkin/{{UPSTREAM}}` first and match its `Background`, its step phrasing and
> its use of Ada and Grace. You are adding scenarios to one file, not writing a second one.
>
> Your staged draft carries a `Feature: {{FEATURE_NAME}}` line matching the target so it parses
> standalone, and a `# --- appended by Slice {{N}} ---` comment above your scenarios. It carries
> **no narrative paragraph and no `Background`** — the upstream file owns both, and the
> coordinator strips your header at consolidation. If your scenarios need a rule the upstream
> paragraph does not state, say so in your return and let the coordinator fold it in; do not add
> a paragraph of your own.

| `{{N}}` | `{{TITLE}}` | `{{PLAN}}` | `{{OUTPUT_PATH}}` | `{{UPSTREAM}}` | `{{FEATURE_NAME}}` |
|---|---|---|---|---|---|
| 4 | Messages: edit and delete | `07-slice-04-implementation-plan.md` | `s4-messages.feature` | `s3-messages.feature` | Messages |
| 6 | Socket write path, optimistic send, typing | `09-slice-06-implementation-plan.md` | `s6-realtime.feature` | `s5-realtime.feature` | Real-time delivery |

---

## Phase 4 — consolidate

You do this yourself. No subagent touches `tests/bdd/`.

- `tests/bdd/features/channels.feature` — append S2's four scenarios below the last existing
  one. Keep the existing narrative paragraph and `Background`; where S2's scenarios rest on a
  rule the paragraph does not state, **fold it into that paragraph** rather than adding a second.
- `tests/bdd/features/permissions.feature` — S2's staged file, header and all.
- `tests/bdd/features/messages.feature` — S3's file, then S4's scenarios appended with its
  `Feature` header and marker comment stripped.
- `tests/bdd/features/realtime.feature` — S5's file, then S6's scenarios appended likewise.

Then reconcile:

1. **Two drafts spelling one step differently is a defect, not a merge conflict.** Rewrite both
   to the frozen vocabulary and record the rewrite. Leaving two spellings pushes the problem onto
   whoever writes the step module.
2. **Rule on every Contract question the writers raised.** You decide these — do not stall the
   run waiting for the user. A ruling that would change something Slice 1 has already shipped
   goes to the user instead.
3. **Amend `00-scenario-vocabulary.md` in place** with any new ruling, as a dated amendment
   blockquote in ch06 style — `> **Amended <date>, after the writers returned.**` — rather than
   rewriting history.
4. **The staged files stay where they are.** They are the audit trail of who wrote what, not
   scratch to be cleaned up.

---

## Phase 5 — two reviewers, in parallel

**Both Agent calls in one message.** They are read-only: they report findings, they never edit.
You apply the fixes.

Give each the same preamble — "The Gherkin for Slices 2–6 of the CollabHub messaging build has
just been written in parallel by separate agents against
`docs/plans/ch06/gherkin/00-scenario-vocabulary.md` and consolidated into
`tests/bdd/features/`. Review it on one lens only. Report findings as
`file:line — what is wrong — what it should say`. Edit nothing." — and then one of:

- **Coverage and fidelity.** "Open each of the five plans (`docs/plans/ch06/05-…` through
  `09-…`) at its `## How the slice runs` section and check the four consolidated feature files
  against it. Every scenario title the plans list appears exactly once · nothing appears twice ·
  no scenario was invented that no plan asks for · nothing a plan explicitly sent to integration
  level has leaked into Gherkin · ruling 6's table in `04-slice-contracts.md` is respected file
  for file. Verify against the actual documents rather than trusting a plausible-looking title."
- **Honesty and harness fit.** "Judge whether each scenario could actually be proved through a
  browser by the `ada` and `grace` fixtures and the page-object methods the plans' `### A.`
  packages specify. Flag: a step asserting on something only a database row or a network trace
  could show · a step naming a `data-testid`, an endpoint, a socket event or a column · a third
  persona · a tag other than `@bdd` and the existing `@smoke` · a `Background` or narrative
  paragraph duplicated by an extending slice · a sleep-shaped step where an event wait is meant ·
  two spellings of what is obviously one step. Also flag the reverse: a scenario so long or so
  conditional that nobody could read it as a contract."

Apply every finding you agree with. Where you disagree with a reviewer, say so in the final
report rather than silently ignoring it.

---

## Phase 6 — verify, report, then stop

```bash
uv run pytest tests/bdd -m bdd --collect-only -q   # what pytest now sees; channels only
```

**That is the only mechanical check this repo has.** There is no Gherkin linter here, and
`permissions.feature`, `messages.feature` and `realtime.feature` are inert — no step module
calls `scenarios()` on them, so they are parsed for the first time when their slice lands. Say
this in your report. Do not imply all four files were validated.

Two consequences to state plainly rather than soft-pedal:

- **The new `channels.feature` scenarios fail from the moment they land**, on missing step
  definitions. This is accepted — Slice 2 is the next slice to be built, so the window is short
  and the red scenarios are the ones about to be worked on. Still run the suite, confirm the
  failures are exactly the four new S2 scenarios, confirm **no previously-green scenario changed
  status**, and report the counts.
- **When Slice 3 is built, its step module calls `scenarios()` on the whole of
  `messages.feature`** — so Slice 4's scenarios run and fail throughout Slice 3's build. Same for
  Slice 6's during Slice 5's. That is inherent in writing the Gherkin ahead of the build, and
  each slice's builder needs to know it before they start.

Then report to the user:

- the files written and the files consolidated;
- every ruling you made in Phase 1 and Phase 4, and why;
- what the reviewers found and what you changed;
- every scenario a writer said it could not express honestly;
- anything left 🔴 that a slice will hit at build time.

Then 🛑 **stop.** The four feature files are presented for approval, and only an explicit
go-ahead moves anything to step 3. A question or a comment on one scenario is not a go-ahead.
Write no step definitions, no page objects, no service code. Do not start building a slice.

---

## Hard rules

- **Never commit.** Stage nothing, run no `git commit`, open no PR. Leave the tree dirty and
  tell the user what changed.
- **Ignore `docs/project/`.**
- **This run touches `docs/plans/ch06/gherkin/` and `tests/bdd/features/` and nothing else.** No
  `src/`, no `docs/design/`, no `pyproject.toml`, no `conftest.py`, no `pages/`, no `steps/`.
- **Slice 7 has no Gherkin and no writer** — ruling 6 gives it three em-dashes. Every scenario
  in its scope was written by Slices 2–6.
- A 🔴 decision that would change something Slice 1 already shipped goes to the user, not to you.
``````
