# Plan review — gh-9, round 3: approved

The one open finding from round 2 is fixed. The 360px tour is now an act and a check: `When Ada
visits every screen at 360 wide` does the tour, and `Then none of them scrolls sideways` only
asserts. No critical or major finding is left open, so the plan is approved for the test pair.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| R2-1. The journey's last step is a `Then` that performs actions (vocabulary §16) | Split into `When Ada visits every screen at 360 wide` (runs `sideways_tour_at_360`, uses `signed_out_context`, stores the result in a function-scoped `tour` fixture) and `Then none of them scrolls sideways` (performs nothing; asserts `tour["result"] == {}`, and a missing key is a `KeyError`, not a pass). The test-approach row, *What no test covers*, the *New* phrases bullet and Task 8's vocabulary entry ("five phrases") are updated to match | **resolved.** Checked with `git diff 9c434c5..8c6ccaf` on the plan. Every place the round-2 review named is changed, and nothing else changed apart from the Review responses. The scenario still ends on a `Then`. The `Then` can't pass by default when the `When` never ran |

## Findings

None.

## Left for later stages

- **Decision 23 (assumed):** acceptance check 3 is done in the order channel draft → open thread →
  reply draft → rotate. The acceptance-reviewer follows that order, not the issue's.
- **Decision 24 (assumed):** Back to channel focuses the channel composer. Crossing to narrow with
  focus in the sidebar focuses ☰. The issue requires neither.
- **Sign-in at 360** is not in the issue's acceptance check 4. The plan's *Corrections* ask the
  acceptance-reviewer to add it.
- **The 360 tour writes to the server:** it starts a DM with Grace. That is harmless in a scenario
  that truncates messaging, but the code pair should know about it.
- **Decisions 13, 16, 17 and 20 (assumed)** stand as recorded, carried over from round 1.
- **For the test-writer:** the `tour` fixture is shared state between a `When` and a `Then` in one
  steps module. Keep it function-scoped, as the plan says, so one scenario's result can't leak into
  the next.

## Checked and sound

- Base: the plan's last change is `8c6ccaf` (plan-writer, round 3) on `feature/gh-9`.
- Length: 559 lines in total, and under 600 with *Review responses* left out.
- Rounds 1 and 2 checked every other section. This final round checked only the responses, as the
  rules say.
