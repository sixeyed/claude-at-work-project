---
name: issue-writer
description: Write a delivery issue for scripts/deliver.sh — a file in docs/issues/ or a GitHub issue — by grilling the user against the exemplar issue, then posting it through the delivery backend and reading it back. Use when the user wants to write, draft or spec an issue for delivery, or turn a feature idea into one. Takes `--backend <local|github>` and `--url <repo URL>`.
---

# Issue writer

The issue is the whole spec `scripts/deliver.sh` gives its seven agents, and nobody is there to
answer a question mid-run. A good one leaves no stage stopping for a human over the spec, and
every stage reading it the same way. Past issues were clear rule by rule and still cost rounds
where the rules **meet**, on **paths** nobody walked, on **assumptions** stated as facts, and on
timing described in words instead of a **timeline**. Those four are this skill's leading words.

The interview itself is **grilling**, as written: this skill doesn't restate its method. What it
adds is aimed at the one reader the issue has — agents that can't ask a follow-up: the facts
gathered first, five branches every requirement must visit, an end you can check, the issue's
shape, and a read-back as the plan-writer.

Where the issue lives is the **delivery backend**'s business, never this skill's: every read and
write goes through the `delivery` CLI (`tools/delivery/`), so the steps are the same for a file
in `docs/issues/` and a GitHub issue.

## 0. Choose the backend

Arguments to this skill win: `--backend local|github` and, for a remote one, `--url` with the
repo's web URL (`https://github.com/<owner>/<repo>`; a `github.com` URL alone is enough). With
no arguments, `DELIVERY_BACKEND` and `DELIVERY_URL` decide; with neither, it is local. Pass
whatever you were given straight to the CLI — it owns those rules — and check it before anything
else, so a wrong URL or a missing login costs seconds, not a grilling:

```bash
uv run delivery [--backend <b>] [--url <u>] check
```

Run every `delivery` command from the repo root, with the same `--backend`/`--url` each time.
Tell the user the backend and repo it printed. If `check` fails, show its message and stop
until they fix it or choose another backend.

## 1. Read the exemplar

Read `docs/issues/exemplar-issue.md` in full. Its sections are the issue's shape, and its
`Why` notes are what past deliveries found missing — the reason for each section. Read
`CLAUDE.md` and `docs/design/07-open-decisions-register.md` too: an issue answers to both.

Done when you can name each section of the exemplar and what went wrong without it.

## 2. Gather the facts

Facts are yours to find, never the user's to supply. From the user's idea, dispatch `Explore`
sub-agents for what the issue will need, and carry on with step 3 while they run:

- the design doc of every service the work touches, and the sections it changes;
- what already exists, in the code's own names — tables, routes, events, hooks, helpers;
- the register entries nearest the work, 🔴 ones above all;
- the nearest past feature to use as a template (a commit), and sibling branches in flight.

Done when every fact the issue will state has a source you can cite.

## 3. Grill

Invoke `mattpocock-skills:grilling` with the Skill tool if it is listed; if not, read
`grilling.md` beside this file — the same skill, vendored — and follow it. Everything it says
holds here, its rule above all that the decisions are the user's: put each to them and wait.
This step adds to its design tree, and to when it is done.

**Five branches hang off every requirement**, however settled it looks — past issues were
clearest exactly where they went wrong. They are questions to put, never answers to supply:
each one asked, with your recommendation, and answered by the user.

- **Meet** — each other rule that touches the same state. When both fire at once, or one
  lands while the other is in flight, what does the user see?
- **Paths** — the rule on each path through the app: first load, a return to something
  cached, a switch while a request is in flight, a reconnect, a second tab or device, lost
  access, an unmount. What must be true on each?
- **Assumptions** — the behaviour of the existing code or a library the rule leans on. These
  are facts, so they are yours: check each by sub-agent against the code and the installed
  source. What you can't confirm goes into the issue labelled as an assumption for the plan
  to check.
- **Timeline** — anything with time or order in it (a throttle, a window, a retry, a
  response racing a broadcast) gets a worked sequence: `t=0 … t=500 … t=1000`, what is
  sent and what is seen.
- **Conventions** — each rule in `CLAUDE.md`'s *Conventions that are easy to get wrong* the
  requirement touches: what it reveals across workspaces or to a non-member, what it does when
  R1 is down, what it keys on. A rule that crosses one is a decision to put, not a detail for
  the plan — a name unique across every workspace tells one tenant what another holds — and,
  once made, an exception to record in the conventions doc, so no reviewer reads it as a breach.

**And for the issue as a whole:** what is decided already, what is left to the plan on
purpose, what is not in this issue, and the acceptance checks — the ones the
acceptance-reviewer proves on the branch's preview. For each check, ask: would it fail on
`main` today, and from what starting state? A check that would pass there too either gets a
starting state that only the change can decide (a user who has never signed in, a page
loaded before the other user acts), or is cut. If running the check spends its state, the
issue names a different user for each check that needs one. A 🔴 register entry the
work depends on can't be built on: put it to the user as a decision to make first, or cut it
from scope.

**Done** when grilling is — the frontier empty, and the user confirming you share an
understanding — and a coverage table, every requirement against Meet, Paths, Assumptions,
Timeline and Conventions, has each cell answered or marked "n/a" with the reason. Show the table with that
confirmation, and write nothing until the user gives it.

## 4. Write the issue

Draft it as two things: a **title** — the feature in a few words, no number — and a **body**
file in your scratchpad directory, starting at the exemplar's first section. No `Issue:` line
and no `# Issue N —` heading: the backend adds what it needs.

- **Shape:** the exemplar's sections, in its order, without its `Why` notes. A section left out
  is left out on purpose — say why in one line where it would have been.
- **Requirements:** numbered, one rule each, in words a test can be named from: "at most",
  "any", "once, not twice", "the latest". Where the rules meet, the paths table, the
  assumptions and the timelines are sections of their own, as in the exemplar. Elsewhere in
  the issue, refer to a requirement as `Req 3` — never `R3`, which is a Redis instance in
  `CLAUDE.md`, and never `§3`, which is a section of a design doc.
- **Length:** 120–250 lines. The agents read all of it; what they need to work out for
  themselves, they will.
- **Line breaks — remote backends:** one line per paragraph and per list item, never wrapped.
  GitHub renders every newline in an issue body as a line break, so prose wrapped at 95
  columns reads ragged on the issue page. Code blocks, tables and the timeline keep their
  lines. Local issues stay wrapped, like every other doc in the repo.

Then post it:

- **A remote backend publishes it.** Name the backend and repo URL and wait for the user to say
  to post it — the coverage-table confirmation is not that. Then make sure the marker label
  exists — `ensure-labels` makes it and the labels that drive a delivery — and create the issue
  with it. `delivery` marks an issue as written for delivery; it does not start one.

  ```bash
  uv run delivery --url <u> ensure-labels
  uv run delivery --url <u> issue create --title "<title>" --body-file <draft> --label delivery
  ```

- **Local** writes `docs/issues/<NNN>.md`, numbered after the highest there. That is a change
  to the repo, so run it from a worktree on a branch, as `CLAUDE.md` says; nothing is
  committed.

  ```bash
  uv run delivery issue create --title "<title>" --body-file <draft>
  ```

`create` prints the issue as JSON, as the backend now holds it. Its `key` — `issue-9`, `gh-12`
— names the issue from here on.

**Read it back** against the draft:

```bash
uv run delivery [...] issue verify <key> --title "<title>" --body-file <draft>
```

Exit 0 is a match. Exit 1 lists what differs: fix it with `issue edit <key> --title … --body-file
<draft>` and verify again — never a second `create`, which leaves a duplicate behind. If it still
differs, show the user the differences and stop.

## 5. Check it

Fetch the issue — `uv run delivery [...] issue get <key>` — and read its `body` once as the
plan-writer will, with no memory of the grilling. Read what the backend holds, not your draft:
it is what the agents will get.

- every exemplar section present, or its absence explained;
- every `Why` in the exemplar answered by something in this issue;
- every acceptance check states what makes it fail on `main`, and none depends on state an
  earlier check has already used;
- every decision the issue makes or changes is recorded everywhere it is stated today —
  search for its register number and its subject, and put each place in *Record in this
  slice* — the register, the design docs, the conventions doc, READMEs. Never `CLAUDE.md`
  or anything under `.claude/`: they state how to work, not what is decided, and no
  delivery stage may write them. A decision that crosses a convention is recorded as an
  exception in the conventions doc and the register, where every reviewer looks. If
  `CLAUDE.md` does restate a decision, tell the user — it is theirs to fix, outside the issue;
- a rule over a class named by example ("X and the like", "such as") has a closed
  definition — a standard, a list, or a check the plan can run — and examples on both sides
  that look alike; a rule over free-form input says what it compares or stores after (trim,
  case, normalisation);
- no sentence two plan runs could read two ways. Each one you find goes back to the user as
  a question, and the issue is rewritten with the answer — through `issue edit`, then `issue
  verify` again.

Then stop — starting the delivery is theirs. Give the user:

- **local:** the path, the key, and the command that starts delivery, `scripts/deliver.sh
  issue-<N>`;
- **remote:** the issue's URL, the key, and the command that delivers it from this machine,
  `scripts/deliver.sh --backend github --url <repo URL> gh-<N>` — and that adding the
  `delivery:ready` label to the issue starts it on GitHub Actions instead. Never add that label
  yourself: starting a run spends money, and is theirs to do.
