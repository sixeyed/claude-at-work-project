# Scenario vocabulary: the words the five feature files share

## Context

Slices 2 to 6 each begin the same way — write the `.feature` file, stop, and wait for approval
before any code exists ([`02-messaging-core-delivery-plan.md`](../02-messaging-core-delivery-plan.md)
§"How every slice runs", steps 1 and 2). That first step is being done for all five **at once**,
one agent per slice, exactly as the plans themselves were written.

Five writers working blind will invent five ways to say "Ada opens the channel". The step author
downstream then has to reconcile them, or — worse — does not, and the suite ends up with
`When Ada opens "general"` and `When Ada selects the "general" channel` bound to two functions
doing one thing.

This document is the answer to that, and it is what [`04-slice-contracts.md`](../04-slice-contracts.md)
is for the code: a set of **rulings**, not a summary. Where it rules on something a writer follows
it and does not re-decide it. Where it does not, and the answer would constrain another slice, the
writer raises a **Contract question** with a recommendation and never a silent answer.

**Binding on all five writers.** Ruling 6 of `04-slice-contracts.md` — "BDD harness growth" — is
binding above this document and says which slice owns which file; nothing here overrides it.

Three facts about the harness shape everything below:

- **pytest-bdd only generates tests for a feature some module calls `scenarios()` on.**
  `steps/test_channel_steps.py:26` does that for `channels.feature` and nothing else does it for
  anything. A new `.feature` file is inert until its slice writes a step module — but scenarios
  **appended to `channels.feature` run from the moment they land**, and fail on missing steps.
- **Every Gherkin tag becomes a pytest marker and has to be declared** in the root
  `pyproject.toml:69`. `bdd` and `smoke` are declared. Nothing else is, and this run adds none.
- **Ada and Grace are the only signed-in users**, and ruling 6 forbids a slice adding a
  session-scoped fixture that signs in a third.

---

## 1. Personas — Ada and Grace, and no one else

🟢 **Two people, fixed.** `tests/bdd/conftest.py:51` signs in `ada@collabhub.dev` and
`grace@collabhub.dev`, once per session each, into contexts that stay alive for the whole run.
Both are moved into the shared `CollabHub Demo` workspace by `SignInPage.use_workspace`, because
each account also owns a personal workspace and two people in two personal workspaces cannot see
each other's channels.

- **Ada administers what she creates.** Whoever creates a channel administers it
  (`channels.feature:13`), so Ada is the admin in every scenario that needs one.
- **Grace is the other member of the same workspace**, and is *not* an admin of Ada's channels
  unless Ada makes her one. When a scenario needs a non-admin, Grace is it.
- **Neither ever signs out.** The `sign-out` control exists (`ChatLayout.tsx:44`) and clicking it
  revokes the refresh token the session-scoped context is holding, ending that user's session for
  every later scenario (S2 gap 9). No step clicks it, in any file.

🔴 **A scenario that seems to need a third person is a Contract question, not a local decision.**
Say so in your return with what the third person was for; do not invent `Hopper`, and do not
reshape the scenario into one Grace can play if that changes what it proves.

---

## 2. Step phrases the suite already has

Quoted verbatim from `steps/test_channel_steps.py`. **Reuse one of these exactly where it fits.**
A phrase you introduce is fine — that is most of what this run produces — but introducing a second
spelling of one of these is a defect.

| Phrase | Source |
|---|---|
| `Given Ada is signed in` | `:47` — the `Background` of `channels.feature`; loads the app fresh |
| `Given Ada has created a public channel named "{name}"` | `:54` |
| `When Ada creates a public channel named "{name}"` | `:62` |
| `When Ada tries to create a public channel named "{name}"` | `:72` |
| `When Grace opens CollabHub` | `:88` — Grace's fresh load, and see ruling 9 |
| `Then Ada sees the "{name}" workspace` | `:96` |
| `Then Ada is looking at the "{name}" channel` | `:101` |
| `Then "{name}" is in Ada's channel list` | `:106` |
| `Then "{name}" is in Grace's channel list` | `:111` |
| `Then "{name}" appears in Ada's channel list exactly once` | `:116` |
| `Then Ada's channel list is empty` | `:137` |

**The complaint idiom.** `Then Ada is told …` is how the suite reports a rejection —
`Then Ada is told that channel name is already taken` · `Then Ada is told a channel name is
required` · `Then Ada is told the name <complaint>`. Behind it, `_COMPLAINTS`
(`test_channel_steps.py:29`) matches **loosely**: the step asserts that a few words appear in what
the user was shown, not that the copy is a particular sentence. That is deliberate, and it is
stated in the module docstring — a scenario says *which rule* was reported, so copy stays editable
without a test failing, while "too short" reported where "must start with a letter" was expected
still fails.

**So: name the rule, never the sentence.** `Then Ada is told the message is too long` is right;
`Then Ada sees "Message must be 8000 characters or fewer"` is wrong.

**Every phrase you introduce goes in your return**, spelled exactly as you wrote it. That list is
what the consolidation pass reconciles.

---

## 3. One `Background` and one narrative paragraph per file — owned by the slice that creates it

🟢 The creating slice writes both. **An extending slice contributes scenarios only.**

- `channels.feature` already has both (`:4-13` and `:15-16`). S2 appends four scenarios and adds
  neither.
- `messages.feature` — S3 writes both; S4 adds neither.
- `realtime.feature` — S5 writes both; S6 adds neither.
- `permissions.feature` — S2 writes both, because S2 creates it.

A staged draft from an **extending** slice still carries a `Feature:` line matching its target, so
it parses standalone, and a `# --- appended by Slice N ---` comment above its scenarios. The
coordinator strips that header at consolidation.

If your scenarios rest on a rule the upstream narrative paragraph does not state, **say so in your
return** and let the coordinator fold the sentence into the existing paragraph. Do not write a
second paragraph.

**The paragraph is the part a non-engineer reads** to check the behaviour is the one they wanted.
It states the rules in the language of the people who use the product — "a public channel is
visible to everyone in that workspace" — never in the language of the schema. `channels.feature`
is the model: two short paragraphs, no jargon, no endpoint, no column.

---

## 4. Tags — `@bdd` on the `Feature` line, and nothing else

🟢 `@bdd` on the `Feature` line of every file. `@smoke` stays exactly where it is, on
`channels.feature:18`, and no new scenario gets it.

Every Gherkin tag becomes a pytest marker, and an undeclared marker is an error under this repo's
settings. `bdd` and `smoke` are declared in the root `pyproject.toml:69`; **declaring another is
out of scope for this run**, which touches no `pyproject.toml`.

🔴 A writer that wants a tag — `@slow`, `@realtime`, `@wip` — raises it as a Contract question and
writes the file without it.

---

## 5. `Scenario Outline` where the rule is a table of cases

🟢 Follow the name-validation outline at `channels.feature:55`: when the rule under test is one
rule with several inputs, it is a `Scenario Outline` with `Examples`, and the varying part is a
`<placeholder>`. When it has one case, it is a plain `Scenario`.

Two things that outline gets right and are worth copying:

- **The `Examples` table carries the input *and* the expected complaint** where they vary together
  (`| name | complaint |`), so one outline covers six rules without six scenarios.
- **Each row is a case, not a variation on a theme.** `ab` is too short, `1password` does not start
  with a letter — different rules, same shape of test. A row that needs a different `When` is a
  different scenario.

An outline whose `Examples` has one row is a `Scenario` that has been made harder to read. An
outline with eight rows over three columns is a spreadsheet. Neither is what this is for.

---

## 6. Browser-observable only

🟢 A step says **what a person did, or what they saw**. That is the whole test.

Not permitted in any step, in any file:

- an endpoint or an HTTP verb — `POST /channels/{id}/messages`, "the API returns 404"
- a status code, a problem `type`, or an `errors` map key
- a socket event name — `message_received`, `join_channel`, `typing`
- a table, a column or a DTO field — `deleted_at`, `version`, `authorId`
- a `data-testid`, a CSS class, or any locator at all. Selectors live in page objects
  (ruling 6 of `04-slice-contracts.md`); a step definition never holds one and neither does a
  scenario.

**If the only way to observe something is a database row or a network trace, it is not a
scenario.** It is an integration test, and each plan already says which of its behaviours are
there instead — see ruling 7 below.

The one deliberate exception in the existing suite proves the rule: "A non-member cannot open a
private channel by its URL" (S2) is about a person pasting a link, which is a thing people do.
The *URL* is browser-observable; the channel id inside it is the page object's business
(`current_channel_id()`, S2 work package A).

---

## 7. What never becomes a scenario

Collected from the five plans' "staying at integration level" paragraphs, so no writer relitigates
it. **Each plan is the authority for its own slice — this is a collection, not a new decision.**

| Kept out of Gherkin | Where it lives instead | Whose plan says so |
|---|---|---|
| **409 version conflict** — two browsers racing a `PATCH` | integration | ruling 3 · S2 · S4 · S6 |
| **403 vs 404** on a write the caller may not make | integration | S2 gap 1 · S4 gap 1 |
| **Cross-workspace tenancy** — a workspace-A token reading workspace-B | integration | S2 · S3 · S4 |
| **The exact problem `type` and `errors` map** of any rejection | integration | S3 · S4 |
| **Cursor mechanics** — `nextCursor` going null on the last page | integration | S3 |
| **409 on renaming into a taken name · 409 last-admin removal** | integration | S2 |
| **The idempotent second delete · `PATCH` on a tombstone · the archived-channel freeze** | integration | S4 gaps 3, 7 |
| **Socket handshake failures** — absent, expired, malformed or service-audience token | integration | S5 |
| **The `access_token` query fallback · room isolation · the publisher no-op** | integration | S5 |
| **The `edit_message` / `delete_message` acks and their rejections** | integration | S6 |
| **The five-second ack timeout · the expired or revoked principal mid-session** | integration | S6 |
| **A member removed while their socket is live** | documented limitation, ruling 20 | S2 |

A scenario that has crept into one of these is not a coverage win. It is a test that asserts on
something a browser cannot see, and it will be deleted by whoever writes the step module.

---

## 8. Waits are events, not sleeps

🟢 No step says "waits five seconds", "waits a moment", or "after a while". A scenario asserts on
**a state the app reaches**; how long the page object waits to see it is the page object's
business, and it waits on an event with an explicit timeout (`ChatPage._settle`, `chat_page.py:50`;
`create_channel_and_wait`, `:65`).

This matters most in the two real-time files, where a sleep is the obvious way to write "Grace sees
it without reloading" and the wrong one:

- **Right:** `Then Grace sees "hello" in the channel without reloading` — the page object waits for
  the row to appear on a page nobody navigated, and the assertion passing *is* the proof.
- **Wrong:** `When Grace waits five seconds` `Then Grace sees "hello"`.

The one place time is legitimately part of the rule — the typing indicator clearing after Ada stops
typing (S6 gap 5) — is still written as a state: `Then the typing indicator clears for Grace`. The
TTL and the timeout comfortably above it are the page object's, not the scenario's.

---

## 9. Ordering is explicit where it matters

🟢 **Until Slice 5 there is no real-time delivery.** A cross-user assertion written before that
must put Grace's load *after* Ada's change, or it asserts on a list her browser cached minutes ago.
S2's plan says this in as many words; **it holds for S3 and S4 too.**

The existing scenario at `channels.feature:33` is the shape:

```gherkin
Scenario: A new public channel appears for another member
  Given Ada has created a public channel named "general"
  When Grace opens CollabHub
  Then "general" is in Grace's channel list
```

Ada's change is a `Given`. Grace's load is the `When`. The assertion is on what she has after the
load. Reversed, it passes or fails on cache timing, which is not a behaviour anyone specified.

**From Slice 5 on this inverts, and the inversion is the point.** S5's scenarios assert that Grace
sees the change on a page she did **not** reload, so a `When Grace opens CollabHub` in a real-time
scenario would destroy the thing under test. In `realtime.feature`, Grace is already looking at the
channel before Ada acts, and the word "without reloading" earns its place in the `Then`.

---

## 10. House rules, briefly

- **Scenario titles are the plan's, not the writer's.** Flesh each into Given/When/Then. Do not add
  one no plan lists; do not drop one a plan does. A title that cannot be written honestly through a
  browser gets your best attempt **and a line in your return** — never a quiet reshaping into
  something easier to test.
- **The order of scenarios in a file is the order the plan lists them.**
- **`And` / `But` continue the previous keyword**, as `channels.feature` uses them. A scenario with
  four `Given`s and no `And` reads like a checklist.
- **Present tense, third person, the user's words.** "Ada renames the channel", not "The channel is
  renamed" and not "Ada should be able to rename the channel".
- **One scenario, one rule.** A scenario long enough to need scrolling, or with a branch in it, is
  not a contract anyone will read.
- Files are UTF-8, two-space indentation under `Feature:`, four under `Scenario:` — copy
  `channels.feature` exactly.

---

## 11. Staging and consolidation

Writers produce **staged drafts** under `docs/plans/ch06/gherkin/`. The coordinator consolidates
them into `tests/bdd/features/`, per ruling 6's table.

| Staged draft | Consolidated into |
|---|---|
| `s2-channels.feature` | appended to `tests/bdd/features/channels.feature` |
| `s2-permissions.feature` | `tests/bdd/features/permissions.feature`, header and all |
| `s3-messages.feature` | `tests/bdd/features/messages.feature` |
| `s4-messages.feature` | appended to `messages.feature`, header stripped |
| `s5-realtime.feature` | `tests/bdd/features/realtime.feature` |
| `s6-realtime.feature` | appended to `realtime.feature`, header stripped |

**The staged files stay where they are** afterwards. They are the record of who wrote what, not
scratch to be tidied away.

**Nothing else in the repository changes in this run** — no `src/`, no `docs/design/`, no
`pyproject.toml`, no `conftest.py`, no `pages/`, no `steps/`. Writing a step definition or a page
object now would break the 🛑 gate the whole protocol is built around.

---

> **Amended 2026-08-15, after the writers returned.** Five writers produced six staged drafts and
> raised twelve **Contract questions** between them. Four of those were the same defect seen from
> two sides — two slices spelling one step two ways — which is exactly what this document exists to
> catch. Rulings 12 to 21 are below. Nothing above is rewritten: where an amendment settles
> something ruling 1–11 left open, it says so, and the original stands as the record of what the
> writers were working from.

## 12. "Opening a channel" — one `When` form and one `Given` form, and they are different acts

Three spellings came back: S2 and S3 both wrote `opens the "{name}" channel`, S5 wrote
`Given Grace is looking at the "{name}" channel`.

🟢 **Both survive, because pytest-bdd forces the distinction.** A step registered with `@when` does
not match a `Given` line — the keyword is part of the lookup — so a `Given` form has to exist
separately whatever the wording. They also mean different things:

| Form | Meaning |
|---|---|
| `When {Ada\|Grace} opens the "{name}" channel` | the act, mid-scenario — clicking into a channel |
| `Given Grace is looking at the "{name}" channel` | the arrangement — Grace has loaded the app *and* is sitting in that channel before Ada does anything |

The `Given` form is what makes ruling 9's inversion possible: from `realtime.feature` on, Grace is
already watching before Ada acts, so "without reloading" is provable. **Neither is a paraphrase of
the other and neither is retired.**

## 13. `Given Ada has sent "{body}" in "{name}"` — the channel is always named

S3 and S4 wrote the channel in; S5 wrote `Given Ada has sent "{text}"` without it, relying on Ada
already being in the channel she created.

🟢 **The long form wins, everywhere.** S5's two occurrences were rewritten at consolidation. A
`Given` that depends on where an earlier `Given` happened to leave the browser is the arrangement
step most likely to break when a scenario is reordered, and naming the channel costs four words.

## 14. `When Ada edits "{old}" to say "{new}"` — S4's spelling, not S5's

S4 wrote `to say "{new}"`; S5 wrote `to "{new}"`.

🟢 **S4's.** S4 is the slice that builds editing and lands first, so its step module registers the
phrase and S5's realtime scenario reuses it. S5's line was rewritten. The general rule: **where two
slices spell one act differently, the slice that owns the behaviour owns the spelling** — the other
is the caller.

## 15. Assertions name whose window they are about

S4 wrote `Then "{body}" is marked as edited`; S5 wrote `Then Grace sees "{text}" marked as edited`.
S3 wrote `Then "{body}" is shown as Ada's message` and `Then "{body}" is shown with the time it was
sent`.

🟢 **Every assertion names the reader**, because two windows are open in half the suite and an
impersonal `Then` cannot say which one it means. The existing suite already does this —
`"{name}" is in Ada's channel list` names the owner of the list, not the channel. Rewritten at
consolidation into one family:

- `Then Ada sees "{body}" marked as edited` · `Then Grace sees "{body}" marked as edited`
- `Then Ada sees "{body}" written by Ada` · `Then Grace sees "{body}" written by Ada`
- `Then Ada sees "{body}" with the time it was sent`

`Then Ada sees "…" written by Ada` reads redundantly and is correct: the scenario asserts that the
author is shown, and it is Ada's window that has to show it.

## 16. A `Then` never performs an action

S5's fourth scenario ended `Then Grace sees "only for general" when she opens the "general"
channel`, deliberately, so the negative assertion above it was not vacuous.

🟢 **The instinct is right and the shape is wrong.** Rewritten as a second `When`/`Then` pair, which
proves the same thing and reuses S3's existing phrases:

```gherkin
When Ada sends "only for general"
Then Grace does not see "only for general" in the channel
When Grace opens the "general" channel
Then Grace sees "only for general" in the channel
```

S3's "Scrolling up loads older messages" already uses that two-pair shape, so it is the file's own
precedent rather than a new idiom.

## 17. Three narrative paragraphs folded, none added

Every extending writer correctly declined to add a paragraph and raised the gap instead
(ruling 3). All three folds were made at consolidation:

- **`channels.feature`** — two sentences: a private channel is only known to the people in it · an
  admin can rename a channel, and the new name follows it everywhere, or archive it, which takes it
  out of the list for good. Raised by S2.
- **`messages.feature`** — one paragraph on edit and delete: the author edits or deletes, a channel
  admin deletes anything said in their channel but never rewrites it, an edited message says so, a
  deleted one leaves a note rather than a gap, and reloading does not bring the words back. Raised
  by S4.
- **`realtime.feature`** — one paragraph on optimistic send and typing: what you send shows
  instantly and settles when the server has it · a refused send is taken back out and the words
  handed back to the box · people are told when somebody is typing and when they stop. Raised by S6.

## 18. `Then Grace sees "{body}" written by Ada` earns its place in Grace's window

S3 flagged that its author scenario runs in Ada's own window, so a rendering path that only ever
resolves the signed-in user's own name would pass it — leaving ruling 14's workspace-directory
lookup untested at browser level.

🟢 **Adopted, as S3 recommended: one extra `And`, no extra scenario.** "Grace sees Ada's message
after reloading" gains `And Grace sees "the eagle has landed" written by Ada`. That is now the only
scenario in the suite that proves a *non-self* display name resolves.

## 19. Kept as written, against the instinct to tidy them

Four writer flags were reviewed and the drafts stand:

- **S2's `But Ada is offered the channel controls`**, asserting on Ada's window inside a scenario
  whose `When` is Grace's. Kept — without the contrast the scenario passes when the controls render
  for nobody, which is a bug the test would then hide.
- **S5's `Then "{body}" appears in Ada's channel exactly once`.** Kept — ruling 17 of
  `04-slice-contracts.md` (the REST sender receives its own broadcast) has no other browser-level
  proof, and it mirrors the existing `appears in Ada's channel list exactly once`.
- **S5's `Then Grace's connection is restored`.** Kept — S5 ships a visible connection status, so
  this is a thing a person sees, and it is what makes the reconnect scenario an event assertion
  rather than a timeout (ruling 8).
- **S3's `Then Ada's message box is empty`** and **S4's `When Ada reloads CollabHub`** alongside the
  existing `When Grace opens CollabHub`. Kept — arriving and reloading are different acts, and the
  suite's idiom is persona-specific steps throughout.

## 20. 🟡 Two scenarios prove the affordance, not the authorization

S4 flagged that "Ada cannot edit Grace's message" and "A non-admin cannot delete someone else's
message" assert only that the control is absent. The rule underneath is a server refusal, which
S4's plan sends to integration level.

🟡 **Accepted, and recorded rather than hidden.** The absent control is the whole of what a browser
can honestly observe, and the refusal is covered where it can be. **S4's builder must land the
matching integration tests in the same slice** — an affordance test alone would let a UI-only guard
pass for a server that has none.

## 21. 🟡 Notes for the step modules, deliberately not in the Gherkin

Three writer findings are real and belong to whoever writes the step definitions, not to any
scenario. Recorded here so they are not rediscovered:

- **Display names are lowercase.** Dex seeds Ada as `ada`, and Auth falls back through
  `name` → `preferred_username` → the email local part. S3 and S6's steps compare case-insensitively
  and keep the names as module constants beside `conftest.py`'s `ADA` / `GRACE`, rather than putting
  a literal in a scenario.
- **`before it is confirmed` races the ack.** S6's optimistic-send assertion can only observe the
  pending state if the read beats the round trip. S6's plan intends exactly that. **If it proves
  flaky when built, it is a Contract question — not a step weakened to "pending or confirmed",
  which asserts nothing.**
- **`When Ada stops typing` is a no-op step.** Stopping is the absence of keystrokes; the assertion
  after it carries the rule. That is correct under ruling 8 and must not become a sleep.

---

> **Amended again 2026-08-15, after the reviewers returned.** Two reviewers — coverage and
> fidelity, honesty and harness fit — read the four consolidated files against the five plans.
> Coverage came back clean on every category: all 34 scenario titles present exactly once, worded
> as their plan words them, nothing invented, nothing leaked from an integration-level exclusion
> list, ruling 6's ownership table respected file for file. The honesty pass found one defect that
> would have made three scenarios pass vacuously, and both reviewers found it independently.
> Rulings 22 to 25 follow, and two clerical errors in the amendment above have been fixed in place
> (six staged drafts, not seven; two rewritten occurrences in ruling 13, not three).

## 22. 🟢 Re-opening the channel you are already in proves nothing — reload first

**Found by both reviewers, independently, and confirmed in the code.** Three scenarios in
`messages.feature` arranged a change and then wrote `When Ada opens the "general" channel` to see
it. Ada was already in that channel: `Given Ada has created a public channel named "…"` runs
`create_channel_and_wait`, and creating navigates into the new channel.

Clicking the sidebar entry for the channel already on screen is a **same-route navigation**.
`ChannelList.tsx:49` is a `NavLink` to `/c/{id}`, `App.tsx:129`'s `ChannelRoute` therefore never
remounts, and `main.tsx:15` sets no `staleTime` or `refetchOn*` that would force a refetch anyway.
Nothing is re-read, so:

- "Scrolling up loads older messages" seeded 60 rows *after* the message query had already resolved
  to `[]`, then asserted the oldest was absent — passing vacuously — and failed on both assertions
  after the scroll.
- "Ada cannot edit Grace's message" and "A channel admin deletes another user's message" asserted
  on a message written into a window holding a stale empty list.

🟢 **The arrangement is `When Ada reloads CollabHub` then `And Ada opens the "general" channel`** —
the shape the tombstone scenario already used and ruling 19 already blessed. Applied in all three
places, with their comments corrected: the comments described the intent accurately and named the
wrong mechanism.

**The general rule this leaves behind:** a step that exists to make a browser see something written
outside it is a **reload**, never a click. A click only ever proves something about navigation.

## 23. 🟢 A negative assertion is anchored to a positive event

`realtime.feature`'s "Grace does not receive messages for a channel she is not looking at" asserted
Grace's absence with nothing to time it against. Nothing changes in Grace's window, so a page object
could only wait a fixed interval before declaring absence — a sleep in everything but name, which
ruling 8 forbids even when the word never appears.

🟢 **Anchored on Ada's side first**, reusing the step the file already has:

```gherkin
When Ada sends "only for general" in "general"
Then "only for general" appears in Ada's channel exactly once
But Grace does not see "only for general" in the channel
```

Ada's row arriving is the event that makes Grace's absence meaningful rather than merely early. The
same send also now **names its channel**, for ruling 13's reason: in the one scenario whose entire
subject is which channel a message lands in, the channel was implicit in the order two `Given`s
happened to run.

## 24. 🟢 The scenario under test is arranged through history, not through the feature above it

`realtime.feature`'s edit and delete scenarios had Grace start watching and *then* Ada send the
message about to be changed — so Grace had to receive the original over the socket before the update
arrived. Each scenario silently depended on the one above it, and exercised "apply an update to a
row I received live", which no plan specifies.

🟢 **Ada sends first, Grace looks second.** Grace loads the message as history; the only live event
in the scenario is the one in its title. Ruling 9 is unaffected — Grace is still watching before Ada
performs the act under test, which is the edit or the delete, not the send.

## 25. 🟢 The rejected send asserts the rollback, not just the refusal

As drafted, "A rejected send is rolled back and the error is shown" was step-for-step identical to
S3's "A message over 8000 characters is rejected" except for one line about the draft. Since S6 moves
the composer onto the socket wholesale, S3's scenario covers the same path afterwards — so the
scenario proved nothing its own title claimed.

🟢 **It now asserts the bubble appeared and was withdrawn**, which is the rollback:
`Then Ada sees that message in the channel before it is confirmed` ahead of the existing refusal and
draft-retention assertions. S6's plan adds `pending_message_bodies()` for exactly this.

## 26. 🔴 Shared step definitions have no home, and S2 hits it first

**Both reviewers raised this and it is the one finding this run cannot fix**, because it is about
step modules and this run touches no `steps/`.

pytest-bdd resolves a step from the module that calls `scenarios()` and from `conftest.py` — **not
from a sibling `test_*.py`**. `Given Ada is signed in` appears in all four `Background`s and
`Given Ada has created a public channel named "{name}"` in all four files, yet both are defined only
in `steps/test_channel_steps.py:47` and `:54`. As written, `test_permission_steps.py`,
`test_message_steps.py` and `test_realtime_steps.py` each have to re-register them — four copies of
the two most-used steps in the suite, which is precisely the defect ruling 2 exists to prevent.
`realtime.feature`'s rejected-send scenario has the same problem against three of S3's steps.

🔴 **The ruling: shared steps move to `tests/bdd/steps/conftest.py`, and S2's builder does it**, as
the first slice to need a second step module. Each `test_*.py` then holds only the steps its own
feature file introduces. **This is a decision for the user, not the coordinator**, because it
refactors a module Slice 1 has already shipped — it is raised in the report accompanying these
files and no code has been changed for it.

Until it is settled, **no slice's builder should copy a step definition into a second module** on
the assumption that duplication is the plan.

## 27. 🟡 S3's acceptance now depends on ruling 14's hook

Ruling 18 added `And Grace sees "the eagle has landed" written by Ada`, making S3's reload scenario
the suite's only browser-level proof that a **non-self** display name resolves. That is inside S3's
scope — its plan already maps `authorId` through `useWorkspaceMembers` — but it means S3 cannot go
green until ruling 14's hook exists, and ruling 14 gives that hook to **S2**. S3's builder should
confirm S2 landed it before starting.

## 28. Reviewer findings not adopted

- **"A sent message appears immediately and is confirmed" asserts four rules."** Kept. The title has
  two halves by construction, the composer clearing is a genuinely new fact once send moves to the
  socket, and dropping `appears in Ada's channel exactly once` would remove ruling 17's only
  browser-level proof.
- **"`permissions.feature` restates rules `channels.feature` now carries."** Partly adopted. A
  feature file is read on its own, so the visibility rule stays; the paragraph was tightened so the
  part no other file states — a link to a private channel is indistinguishable from a link to
  nothing — leads it.

---

> **Amended a third time 2026-08-15, at the user's direction, after the files were presented.**
> Writing five slices' Gherkin ahead of the code leaves 23 scenarios describing behaviour nothing
> implements — red from the moment they land, and a suite expected to be red is one nobody reads.
> Rulings 29 and 30 fix that with two tags, **which overturns ruling 4's "`@bdd` and nothing else"**.
> Ruling 4 stands as the record of what the writers were working from; the tags below are added by
> the harness, not by a scenario writer, and no writer chose one.

## 29. 🟢 `@pending` — merged, visible, skipped

Every scenario whose slice is not yet built carries `@pending`. `tests/bdd/conftest.py` implements
`pytest_bdd_apply_tag` and turns that tag into `pytest.mark.skip` — the hook is `firstresult=True`,
so returning a value short-circuits pytest-bdd's default, which would apply a marker of the same
name and **run** the scenario. Every other tag returns `None` and falls through to that default, so
`@bdd` and `@smoke` are untouched.

The tag is declared in the root `pyproject.toml` anyway, so it still resolves if the hook is ever
removed. Skipping — rather than deleting, branching or commenting out — is what keeps the contract
reviewable in the place it will eventually run.

🟢 **Each slice's first build step is to delete `@pending` from its own scenarios**, then watch them
fail for the right reason. **Nobody deletes it from anyone else's.** This is what stops S4's five
scenarios running throughout S3's build, and S6's three throughout S5's — the consequence flagged
when these files were presented, and the reason this ruling exists.

## 30. 🟢 `@s2`–`@s6` — which slice delivers the scenario

Alongside `@pending`, each scenario carries the slice that owns it, so one slice's contract can be
read on its own. These are ordinary markers — declared in `pyproject.toml`, applied by pytest-bdd's
default handling, not intercepted.

**Today the tag is read in the `.feature` file**, which is where a review of a contract happens
anyway. `-m` selection is the bonus and it arrives per slice:

```bash
uv run pytest tests/bdd -m s2 --collect-only -q   # 4 scenarios — channels.feature is wired
uv run pytest tests/bdd -m s3 --collect-only -q   # nothing yet — see below
```

`messages.feature`, `permissions.feature` and `realtime.feature` are **inert**: no module calls
`scenarios()` on them, so pytest generates no test functions and there is nothing for a marker to
select. Each becomes selectable the moment its slice writes its step module — `-m s4` works from
the start of S3's build, `-m s6` from the start of S5's. That is the same inertness that makes the
`@pending` skip cost nothing on those three files today; the tag matters there for what it does
*next* slice.

🟢 **A slice drops its own `@sN` once it has delivered and its scenarios are green** — the last step
of the slice, where `@pending` is the first. The two tags have different lifetimes on purpose:
`@pending` says *not yet built*, `@sN` says *this is the batch under review*. After Slice 6 no
feature file carries either, and the `s2`–`s6` declarations go with them.

**A tag left behind after its slice ships stops meaning anything**, which is the failure mode worth
naming: the marker is a review aid with an expiry date, not a permanent label.

---

> **Amended a fourth time 2026-08-16, in review.** The question asked of the presented files: do S2
> and S3 need scenarios covering messages in a private channel — Ada adds Grace, Grace opens it,
> reads and replies — or do the separate permissions and messages scenarios already compose to that?
> Ruling 31 answers it, and ruling 32 records the one gap the question exposed, which turned out not
> to be about messages at all.

## 31. 🟢 No scenario puts messages in a private channel — it is the case that cannot catch the bug

The composition argument is right, and the code makes it stronger than "probably redundant".

**`get_visible` is not a second visibility path.** `channels.py:199` is `_visible_query(...)` plus
`.where(Channel.id == channel_id)` — the same
`or_(kind == PUBLIC, ChannelMember.user_id.is_not(None))` predicate that builds the sidebar. There
is nowhere else private-membership visibility could be got wrong.

**And a private channel with a member is the one case with no discriminating power.** Ruling 12
exists to stop `messages.py` guarding on `channels.is_member(...)` instead of
`channels.get_visible(...)` — the mistake doc 02 §3.1's "channel member" invites. For a *member of a
private channel* both functions return true, so such a scenario passes under the wrong guard as
happily as the right one. It would test less than what is already there.

**The discriminating case is public plus non-member, and the suite carries it twice.** `create`
gives the creator an `ADMIN` membership row (`channels.py:184`), so every Ada-only scenario passes
under either guard and it is Grace who does the work:

| Scenario | What it forces |
|---|---|
| `messages.feature` — "Grace sees Ada's message after reloading" | a non-member **reads** a public channel. Fails immediately under `is_member` |
| `messages.feature` — S4's two `Given Grace has sent "…" in "general"` | a non-member **posts** to a public channel — ruling 12's other half, in the arrangement |

🟢 **So: no private-channel message scenario, in S2 or S3.** Re-proving body validation, author
rendering and send mechanics against a different channel kind is duplication, and it would drag S2's
`create_private_channel` / `add_member` page objects into S3's file, coupling two slices for no
coverage.

🟢 **The positive private case goes to integration instead**, where it costs two cases in a module
already being written: a member of a private channel `GET`s and `POST`s its messages successfully.
S3's plan carries it in `tests/test_messages.py` beside the 404 for a non-member, which was already
there. That is the honest level for it — membership composing with the message routes is a server
rule, and no browser adds anything to the proof.

## 32. 🟢 Something does have to open a private channel

The question exposed a real gap, and it was not the one asked about: **all four permissions
scenarios stopped at the sidebar.** The suite proved a private channel is *listed* for a member and
proved the *refusal* for a non-member following a link — but nothing ever opened one successfully.
"An admin adds a member to a private channel and they can see it" asserted only that it appeared in
a list, which is less than its title claims.

🟢 **Fixed in place, with two steps and no new scenario**, in the two-pair shape ruling 16 settled:

```gherkin
When Grace opens CollabHub
Then "launch-plans" is in Grace's channel list
When Grace opens the "launch-plans" channel
Then Grace is looking at the "launch-plans" channel
```

`When Grace opens the "{name}" channel` the file already had. **`Then Grace is looking at the
"{name}" channel` is new** — the Grace half of `test_channel_steps.py:101`, and the only step phrase
this review round added.
