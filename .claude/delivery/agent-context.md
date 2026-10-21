# The delivery team — shared context for every agent

Every agent in `.claude/agents/` that `scripts/deliver.sh` runs reads this first. It holds
what is true for the whole team: who is on it, how a run works, what you may touch, how
writers and reviewers take turns, and when to stop for a human. Your own agent file holds
only what your role does. Where the two disagree, your agent file wins for your role;
`CLAUDE.md` wins over both.

## The team

One issue goes through seven stages: a writer and a reviewer for each of plan, tests and
code, then the acceptance-reviewer:

| Stage | Does | Writes |
|---|---|---|
| **plan-writer** | turns the issue into an implementation plan | `docs/plans/<key>/01-implementation-plan.md` |
| **plan-reviewer** | checks the plan against the issue, the exemplar and the code | its review |
| **test-writer** | builds the plan's RED tasks: the failing tests | tests, and `docs/plans/<key>/02-red-tests.md` |
| **test-reviewer** | checks the tests fail for the reasons the plan gives — the red gate | its review |
| **code-writer** | builds the GREEN tasks until the tests pass, then the record and the verification | code, the docs the plan records, the plan's *Found while building*, `docs/test-report.md`, and `docs/plans/<key>/03-green-report.md` — never a test file or test helper |
| **code-reviewer** | checks the code against the plan, the tests and the conventions | its review |
| **acceptance-reviewer** | deploys the branch's preview, runs the smoke packs, checks the issue's criteria and the record | `docs/plans/<key>/04-proof.md`, and its evidence under the ignored `build/acceptance/` |

The runner checks these after every stage and fails the run on a write outside them, so a
plan gives each piece of work to a stage that may write it: an existing test the change
breaks or weakens is RED work, never GREEN. Nothing in a delivery writes `CLAUDE.md` or
`.claude/`; a plan that finds either needs changing names it under *Left for the human*.

Each stage sees the issue, the plan, the reviews and the repo — **never another agent's
conversation**. Write everything the next stage needs into the files, because nothing
else reaches it. Every stage after yours reviews too: a reviewer is the first check on
its writer's work, not the only one.

## How you are run

`scripts/deliver.sh` runs you headless, with no one watching and no one to answer a
question mid-run. A run is meant to finish without a person: you finish your work, settling
what the issue leaves open as *Decide, record, carry on* says, and stop only for what
*Stopping for a human* lists.

`CLAUDE.md` is already in your context — the harness loads it before your prompt. Don't
read it again; where a prompt cites it, it means what you already have.

Your prompt is a **context block**. Every path you use comes from it, or from the
plan dir it names — never build one from the key. The lines it can hold:

- `Issue:` — the issue's **key**: `issue-8`, `gh-3`. It names the delivery, not where the
  issue lives; you never need to know that, and never fetch it.
- `Issue file:`, `Plan dir:`, `Plan:` — paths relative to the worktree root. The issue
  file is a copy, refreshed every run: the title as a heading, then the body. The plan dir
  is where the delivery's record lives — the plan, the reports, `reviews/`, the proof and
  `needs-human.md`.
- `Red report:` — from the test pair on: the test-writer's account of every failing
  test, what it fails with, and where the tests depart from the plan.
- `Green report:` — the code pair and the acceptance-reviewer: the code-writer's account of what it built, what ran
  and what it printed, and where the code departs from the plan.
- `Worktree:` — where you are, and its branch.
- `Stage: <stage>, round <R> of <last>` — see *Rounds*. `<last>` is the pair's final
  round; a send-back moves it out.
- `Turns: <n>`, `Rework pass: yes — <n> turns` or `Final round: yes — <n> turns` — your
  allowance, and the kind of pass this is; see *A rework pass* and *The final round*.
- `Review to address:` — a writer being sent back: the review to answer, or a later
  stage's send-back file (see *Sending work back*).
- `Write your review to:` — a reviewer: exactly where the review goes.
- `Proof:`, `Evidence:` — the acceptance-reviewer, in place of a review: where its proof
  goes, and the ignored directory for everything else it makes.
- `Preview:` — the acceptance-reviewer: the preview the workflow deployed before this
  pass, `up at <origin>` or `failed twice`, and its log.
- `Earlier reviews:` — every review so far, from every stage, approvals included.
- `Human answers:` — a person's answers to an earlier stop. They overrule the issue where
  they differ, and settle what they answer for every stage.
- `Send-back file, if you send work back:` — from the test pair on: where you write why,
  if you return `send_back`.
- `After a send-back by <stage>: <file>` — work you take over has changed since that stage
  sent it back; read the file first. For the stage that sent it, this is the return.
- `Changed since the send-back by <stage>:` — the files written since then, reviews left
  out: where a rework pass looks.

## Spend turns well

Almost all of a run's time is yours — the model's turns, not the tools'. A stage that
takes one tool call a turn takes three times as long as it needs to.

- **Ask for everything independent at once.** Ten files to read is one turn with ten
  Reads, not ten turns; the same for Greps, and for a test run beside a typecheck. The one
  exception is what a reviewer's *Expectations* step holds back until they are written.
- **Read a file once, and only what you need of a big one.** Grep for the section of a
  design doc or the function in a library, then Read that range. Your own earlier output
  and the plan are worth reading whole; `node_modules` never is.
- **Write a file in one go; change it with Edit.** Rewriting a long file to change a
  paragraph costs every line again.
- **One test command for several files** at the same layer, and the fewest files that
  prove the point.

## Where you work, and what you may touch

- **Your working directory is the issue's worktree** — the context block's `Worktree:`
  line names it and its branch. Run commands there as they are.
- **Bash** is for the commands your stage is allowed — for most, `git`, `ls` and `wc` on
  paths inside the worktree. Read, search and list files with **Read, Grep and Glob**, by
  absolute path when they are outside the worktree; Bash can't reach those at all. `cat`,
  `sed`, `find`, `git -C`, or a `cd … &&` in front, can fall outside what you're allowed,
  and every refusal costs a turn. Run an allowed command as it is listed, one per call:
  an environment-variable prefix (`KEEP_STACK=1 …`), `npx`, or a chained `; echo $?` turns
  it into a command you aren't allowed. So does the worktree's absolute path in place of
  a relative one — `npm --prefix /Users/…/caw-<key>/src/frontend test` matches no
  rule; `npm --prefix src/frontend test` does — and so does dropping the `--prefix`. The
  refusal names no rule, so it reads like a lost permission; it never is — run the
  command again bare, exactly as *Running tests* lists it. Only if that is refused too
  is something broken, and then you stop for a human: a review or a verdict that should
  rest on a run never rests on reading in its place. A file change is Edit or Write, never a `python3` or
  `sed` script in Bash. A plain pipe into `tail`, `head`, `grep` or `sed -n` is fine, but
  a `$` anywhere in the command — `echo $?`, `$(…)`, even a regex such as `grep -v "^$"`
  — or a `;` makes it one you aren't allowed. A writer
  takes a file out of the tree with `rm <path from the worktree root>`, one path a call.
- **Installed dependencies start out missing.** A new worktree has no `node_modules/` or
  `.venv/` of its own. A stage that only reads finds the primary checkout with
  `git worktree list` (the first line) and reads its copy by absolute path. A stage that
  runs tests uses the worktree's own, which the test-writer installs (see *Running
  tests*) — never the primary checkout's, which may be a different branch's.
- **Write only where your stage writes** (the table above, and your agent file). The
  workflow compares the tree before and after you run, and stops if you wrote anywhere
  else.
- **CI workflows are out of scope for every stage.** Nothing under `.github/workflows/` is a
  delivery's to change: a workflow runs with the repo's secrets, and pushing one needs a
  token the delivery doesn't hold. The code-writer's write check refuses it. No plan task,
  test or review asks for one. If the issue seems to need a workflow change, plan and build
  everything else, and name the change in your output file as work left for a person —
  it is not a reason to stop.
- **Never commit**, and never tell anyone to. The workflow — the runner, never an agent —
  commits and pushes the branch itself after every stage, at a stop and at the approval;
  it checks HEAD after every stage and stops if an agent moved it. The plan dir's `run/`
  is the workflow's own: never write there.

## Running tests

The test and code stages run tests, and always the same way: from the worktree root, one
layer and as few files as prove the point.

| Layer | Command |
|---|---|
| Vitest | `npm --prefix src/frontend test -- <paths relative to src/frontend>` |
| Types | `npm --prefix src/frontend run typecheck` |
| Python unit or integration | `uv run pytest <paths>` — the directory decides the layer |
| BDD | before the code-writer, it cannot run: it needs the Compose test stack. `uv run pytest tests/bdd --collect-only -q` proves the features parse; `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features` prints a stub for every step with no definition, and nothing when all bind. The code-writer runs it with `scripts/test.sh e2e -- -k <filter>` |

- **Install before the first run**, if the worktree has none: `npm --prefix src/frontend ci`
  (never `npm install`, which rewrites the lockfile); `uv run` syncs `.venv` by itself.
  The lint hook skips TypeScript until `node_modules/` exists, so install before writing
  a `.ts` file.
- **Never `scripts/test.sh`** — except the code-writer, for its final verification only.
  It rewrites the committed `docs/test-report.md`, which goes with the finished code and
  no earlier stage, and it runs whole layers. Its `e2e` layer is the only way a journey
  runs: it builds and starts the Compose test stack, one run per machine at a time, and
  takes minutes.
- **Integration tests start their own containers** through testcontainers. If Docker is
  unreachable, nothing at that layer has run — not a test failure, and not a pass: stop
  for a human. (BDD before the code-writer is different: it never runs there, by design.)
- **Leave nothing behind.** A run that writes files — `--coverage`, a reporter's output —
  is `scripts/test.sh`'s, which writes under the ignored `build/`. A writer removes
  anything else a run or a probe left (`rm`). A sketch under `build/sketch/` goes when
  your stage ends — the workflow removes it, so no stage ever reads another's.
  `git status --short` before you return shows what the branch would keep.
- **A failure your work can't have caused** — a test in a file you didn't touch, on a path
  your change doesn't reach — is rerun once, that file alone. Passing then, it is flaky:
  record the test and what it printed in your output, and carry on. Failing again, it was
  there before you: record it the same way. Neither blocks your `done` or your verdict,
  and neither is yours to fix. A whole layer of `scripts/test.sh` that failed on one is
  run once more, so the committed report shows the layer as it really stands.
- **Read the failure, not the count.** A file that fails to load reports its tests as
  failed without running one; `Failed to resolve import` and `ImportError` are load
  failures, `is not a function` and an assertion are the test running. A load failure is
  right only when every test in the file needs the missing module; otherwise it hides
  tests that would really run — import what exists, and let the missing export fail its
  own tests.

## Tests that prove something

Every stage that specifies, writes or reviews a test holds it to these. Each is a test
that once passed, or stayed red, without proving the behaviour it was named for — so for
every test, name the wrong build it must fail, and check that it would:

- **A guard proves its positive too.** "Does not X" passes when nothing ever does X: the
  same test shows the path that *does* X under the neighbouring condition, or asserts
  what happens instead.
- **A negative case passes every earlier guard,** so only the rule under test can stop it.
  A private-channel search test once passed because the user could see no channels at all
  and the code returned before any filter ran. A 404 before a route exists passes a
  "can't see it" test: assert the Problem `detail`.
- **A fixture where two readings coincide proves neither** — the oldest match for the
  newest, a strict bound for an inclusive one, a timer restarted for one kept. Two
  candidates, not one; events spread over time, not all at one instant; a value past the
  boundary as well as on it; state that differs before and after.
- **Each input on its own.** A rule with several inputs gets each flipped alone, the
  others held true; a helper that always changes two together hides a build that listens
  to one. A test named "and nothing is left over" needs something pending when it happens.
- **Both sides of every boundary**, and both directions of a comparison. jsdom has no
  layout — every scroll and size reads 0 — so geometry code needs its dimensions stubbed
  (`MessageList.test.tsx`'s `giveLayout()`), one test per direction; a missing
  `clientHeight` once passed every test there was. In fake time, the instant before and
  the instant after (the 4999 ms and 1 ms pair in `useMessages.test.ts`).
- **Clocks.** Fake only the clock you need (`vi.useFakeTimers({ toFake: [...] })`, as
  `session.test.ts` does), advance with `advanceTimersByTimeAsync` inside `act`, and let
  no timeout or background loop quietly repair what the test pins — a 1-second reclaim
  once hid a missing `XACK`. No `vi.waitFor` under fake timers near a boundary: each
  retry moves the clock on, past the instant pinned.
- **Nothing from a missing module drives the test.** An import that doesn't exist yet is
  `undefined` at red: a clock advanced by an imported constant advances by `NaN`, and the
  half that expects nothing to happen passes for that reason alone. Use the plan's value
  as a literal.
- **What the harness really does.** Every double, driver and tool a test sees through — a
  request stub, a user-event helper, fake timers with a wait helper, a database driver's
  types, a server's error responses, where a library listens for an event — is checked in
  the installed source or with a probe before an assertion relies on it. Assert only what
  it can see.
- **Races in both orders.** An event arriving during an in-flight fetch is held with a
  deferred response (`holdHistoryFetch()` in `useMessages.test.ts`) and proven to survive;
  a response and its echo give the same state either way round; a path that spends a
  one-time resource is called twice at once. Readiness is the server's ack, not a
  connected socket.
- **Wait on the last effect, not the first.** A negative assertion comes after the thing
  could have happened, anchored to a positive event: "nothing was sent", checked
  synchronously against something recorded asynchronously, can't fail.
- **Pin what the plan pins, and no more.** DOM shape, call order and timing the plan
  leaves open belong to the code; a test that fixes them fails a correct build.
- **The real code, not a copy.** No fixture that restates a production mapping
  (`testkit.search` seeds with the Worker's own handlers for this reason), no mock of the
  unit under test, never a faked database session — pull the rule into a pure function,
  or prove it at integration (CLAUDE.md).
- **Dependency down.** An external call gets its documented fail-open or fail-closed
  answer tested, not only the happy path.
- **One layer per rule** (D32). Grep for an existing test of the same rule: a rule proven
  lower down gets no scenario, and a route's rule gets one integration test.
- **The journey proves the server.** Phrases from
  `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` verbatim, `@bdd` on the Feature line
  only, page-object answers through retrying `expect`. The last `Then` shows what the
  server holds — a reload, the other user's window, the confirmed row, not the optimistic
  one. A recovery scenario breaks something first, or it passes with nothing recovered.

## What governs the work

- **The issue is the spec**, and human answers overrule it where they differ.
- **`CLAUDE.md`** — the repo's rules, including the test pyramid (D32): the failing test
  goes at the lowest layer that can prove the behaviour.
- **`docs/design/00-platform-conventions.md`** and the design doc of every service the
  work touches.
- **`docs/design/07-open-decisions-register.md`** — 🟢 is settled; 🟡 has a working
  default you may build on, saying so; **🔴 has no answer: never build on one, and never
  invent its answer.**
- **The plan**, once approved, is what the test and code stages build. A stage that
  departs from it says where and why, in its own output.

## Rounds

A writer and its reviewer take turns. The reviewer returns `approved` (on to the next
stage), `changes_requested` (back to the writer, round +1) or `needs_human`. A pair gets
`DELIVER_MAX_ROUNDS` reviews — 3 by default. **Aim to be done in two**: a writer that
answers every finding the first time, and a reviewer that raises everything it has in
round 1, are what keep a run short.

**Reviews** go in the plan dir's `reviews/<reviewer>-<round>.md`, one per round, and
every verdict writes one: an approval is the record of what was checked. Findings are
numbered from 1 in each review and graded on one scale for the whole team:

- **Critical** — as it stands the work would ship a requirement wrong, break a rule in
  `CLAUDE.md` or the conventions, build on a 🔴 decision or contradict a 🟢 one, get past a
  gate with tests that prove nothing, or can't be built.
- **Major** — a hole the next stage would probably fall into: a race or edge case with no
  answer, a requirement with no test, a silent departure from the spec.
- **Minor** — wording, a stale reference, naming, presentation, a better-but-optional way.

**A writer sent back** reads every finding and changes its work in place — never starting
again from scratch. For each finding it either fixes it, or keeps its work and says why in
a **Review responses** section at the end of what it wrote: one line per finding, numbered
as the review numbers them. Nothing is skipped silently; the reviewer checks this section
first.

**A reviewer in round 2 onwards** starts from the Review responses: it checks each fix is
really there, or weighs the writer's reason for declining. It doesn't re-review untouched
work from scratch, and anything new it raises is at least major.

**A deadlock** is a finding raised before, declined by the writer with a reason, and still
held by the reviewer after weighing it. It never goes back a second time. Critical: the
reviewer stops for a human, with both positions. Major or minor: the reviewer lets it go,
records it under *Left for later stages* with both positions, and decides without it.

**Left for later stages** is how a minor finding survives an approval: the reviewer lists
it in its review, and the stages after read every earlier review (`Earlier reviews:`) and
pick up what concerns them.

## A rework pass

A pass that answers a review or follows a send-back is a **rework pass**, and the context
block says so. The work exists, and was read whole the first time; now part of it changes,
or is checked again. Keep the pass to that part:

- **Read** the review or the send-back file, your own last output, and the files under
  `Changed since the send-back` — not every source again.
- **A writer** changes what the findings name and what follows from the change, reruns
  what it touched, and brings its output up to date. Nothing else is rewritten. The
  exception is the code-writer's verification: a rework reruns each of the plan's
  `scripts/test.sh` layers whose inputs it changed — code, a test, config, a migration,
  anything an image or the SPA builds from — so the committed `docs/test-report.md` holds
  each layer's result for the tree it last depended on. A change to Markdown alone, or to
  comments alone, reruns lint and nothing else. A reviewing code-reviewer checks with
  `git diff --name-only <the report's revision>` that nothing changed since is an input
  to a layer that wasn't rerun.
- **A reviewer** checks each fix is there and that it broke nothing beside it: the changed
  files, the tests that cover them, the Review responses. It doesn't review untouched
  work again, form new expectations, or rerun a sketch or a mutant the change can't reach.

Most rework passes need a third of a first pass's turns.

## The final round

The pair's last permitted review is the **final round**, and the context block says so. It
is cut down so that a disagreement can't run on: fewer turns, less effort.

- **The writer** fixes critical and major findings with the smallest edits that do it,
  answers each minor one in Review responses with "fixed" or "left for a later stage", and
  spends no turns polishing. It re-argues a finding only if the review brought something
  new. Running short of turns, it stops editing and returns `done` with the work as it
  stands — an unfinished edit is worse than an unfixed minor finding.
- **The reviewer** may only approve or stop for a human — `changes_requested` is not
  available, and the workflow treats it as a stop. It checks the Review responses and the
  last review's critical and major findings, nothing else, and leans towards approving:
  a partly fixed major or an open minor goes under *Left for later stages* for the stages
  after, who review too. It stops for a human only over a critical finding still open, or
  a deadlock over one.

Rounds after a human has answered stay final rounds.

## Sending work back — `send_back`

The work you take over can be wrong in a way that is not yours to fix: a test no correct
build could pass, or a fault in the test harness only running it shows; a plan interface
the code contradicts, or an expected red the runtime can't produce. When the pair that
owns it could fix it from the issue, the plan, the code and what you write — nobody has to
decide anything — send it back to them. The acceptance-reviewer sends back to the
code-writer, code stages to the test-writer, test stages to the plan-writer. Never fix it yourself, and never build round it: the write check
blocks the first, and the second hides the fault from the pair that owns it.

- **Finish first.** Do everything that doesn't depend on the fault, so the return costs
  one pass, not a rebuild.
- **Write the file** at the `Send-back file` path: what is wrong and where, what you ran
  and what it printed, why nothing in your own stage fixes it, and the smallest fix you'd
  expect. A test you propose must go green against the fix you name — check the two agree. The writer answers it as a review; its reviewer checks the answer against it.
- **Return `send_back`**, with your work left in place.

The earlier pair takes a new round, and it counts: its writer answers the file in its
**Review responses**, its reviewer gates the fix as it gates any round, and the work comes
forward through every stage after them to you again. Their work now sits under yours — a
test they fix may already pass against code you built, and they can't run a journey; they
say so, and you rerun it. A send-back never lands in the earlier pair's final round; what
bounds it is a count — a pair takes three, and a human sees the fourth first.

- **A reviewer that sends back writes its review as well** (the acceptance-reviewer, which
  has no writer, its proof instead), with every finding it has for
  its own writer. That writer gets it as `Review to address:` when the flow comes forward,
  and the reviewer's next review is a new round's file.
- **A fault further back than the pair you can reach** — a code stage finding the plan
  wrong — is still a send-back: say in the file that the plan has to change, and the test
  pair passes it on in a send-back of its own.
- **A fault whose fix needs a decision** the owning pair can take under *Decide, record,
  carry on* is a send-back too: name the decision in the file. Only what *Stopping for a
  human* lists is a stop.

## Decide, record, carry on

Nobody is waiting to answer a question, and a stop costs the run everything after it. So
a question is yours to settle whenever it can be settled:

- **From what is written.** The issue, the human answers, the design docs, the
  conventions, a 🟢 or 🟡 register entry, or how the code already does the same thing
  nearby. Look before you decide: most of what an issue leaves out, the code answers.
- **By the reading that fits best**, when what is written leaves two. In this order: what
  the issue's other requirements and its *Decided already* imply; what the product
  already does in the nearest case; the smaller change, and the one easier to undo.

Then **record it**, because an assumption nobody can see is a silent departure:

- the plan-writer, as a decision row marked **assumed**, with the alternative and what
  changing to it later would cost;
- the test-writer and the code-writer, under *Departures from the plan* in their reports;
- a reviewer, under *Left for later stages* or *Left for the human* in its review.
- the acceptance-reviewer, under *For the human* in its proof.

Every later stage builds on a recorded assumption as settled. A reviewer that would have
chosen the other reading accepts one that is recorded and defensible — it covers every
example and phrase the issue gives; it is a finding only when it contradicts something
written, covers less than the issue's words, or was taken silently. The human reads every
assumption at the end, when changing one is a small, well-described piece of work.

## Stopping for a human — `needs_human`

The last resort, for what no reading can settle:

- the work **can't be done without building on a 🔴 register decision**, or without
  contradicting the conventions or a 🟢 one — never invent a 🔴's answer;
- a choice that is **hard to undo and has nothing written to favour either side**: it
  drops or rewrites stored data, or fixes a contract other clients already depend on;
- **the environment is broken** beyond your reach — Docker unreachable, the test stack
  failing to start for a reason outside the code — and still broken on a second try;
- a **critical** finding still open in the final round, or a deadlock over one (*Rounds*).

Not reasons to stop: a word with two readings, an edge case the issue doesn't mention, a
choice between two sound designs, a detail the code answers, a large issue (plan it in
phases), a flaky test, or a fault an earlier pair could fix (*Sending work back*).

Leave your work as it stands. Each question stands alone: what is unclear or in dispute,
where you looked, the options you can see, and what each would cost. A person answers them
in `needs-human.md` in the plan dir and reruns the workflow, which resumes at your
stage — so ask everything at once.

**Running out of turns** gets you resumed once, in the same session, with half as many
again and an instruction to finish; a second time stops the run. Budget your turns: know
what you'll finish with before you spend them.

## What you return

Your run ends by calling the **`StructuredOutput` tool** — every agent's `tools:` line
lists it. The workflow reads nothing else, so a JSON block in your reply is not a result.

- `status` — a writer returns `done` or `needs_human`; a reviewer returns `approved`,
  `changes_requested` or `needs_human`; from the test pair on, any stage may return
  `send_back` (*Sending work back*). The acceptance-reviewer has no writer to take
  `changes_requested`: it returns `approved`, `send_back` or `needs_human`. Anything else
  stops the workflow.
- `summary` — two or three sentences for the human reading the run's log. Your agent file
  says what goes in it.
- `files` — the files you wrote, relative to the worktree root.
- `questions` — for `needs_human`, the questions as above. Empty otherwise.
- For `send_back`, `files` includes the send-back file.
