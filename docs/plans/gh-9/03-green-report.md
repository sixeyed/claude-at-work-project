# Green — gh-9, round 1

Built the phone layout: `useNarrow`, a modal drawer behind ☰ in `ChatLayout`, covering thread and member panels in `ChannelView`, the 360px fixes, and the record (doc 06, D48, ADR, vocabulary §36). Every test and check is green, the phone journey included, on its first e2e run.

## Baseline
`useNarrow.test.ts` failed to load (3 tests); `App.narrow` and `ChannelView.narrow` ran with 38 failed and 1 passed by design (`wide / shows the sidebar and no ☰`). The red report's counts hold. Typecheck had its one `./useNarrow` error.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 4 | `lib/layout/useNarrow.ts`, `index.html`, `index.css` | `useNarrow.test.ts` 3 passed | matchMedia is called in `subscribe`/`getSnapshot`; `#root` is `100dvh` |
| 5 | `ChatLayout.tsx`, `ChannelList`, `DirectMessageList`, `WorkspaceSwitcher`, `SearchBox` | `App.narrow` 33 passed | `onNavigate` on four components; `onCreated` navigates then closes |
| 6 | `ChannelView`, `ChannelHeader`, `MemberPanel`, `ThreadPanel` | `ChannelView.narrow` 6 passed | covering overlay, `inert` column, Members button, Back to channel |
| 7 | `AttachmentList`, `MessageItem`, `SearchResult`, `ChannelHeader` | journey's 360 tour passed | see Departures |
| 8 | doc 06, register D48, ADR `261123-a-responsive-layout-below-768px`, vocabulary §36 | — | sweep found nothing saying narrow isn't built |

## What ran
- `npm --prefix src/frontend test`: 63 files, 662 passed (baseline 620 + 42).
- `npm --prefix src/frontend run typecheck`, `run lint`, `run build`: clean.
- `scripts/test.sh lint unit`: passed; unit 2141 (baseline 2099).
- `scripts/test.sh e2e`: passed, 27 passed, 0 failed (baseline 26 + the phone scenario). Last run after the last code change.
- `python3 .claude/hooks/checks/conventions.py` on the changed `.tsx`/`.ts`/`.css`/`.html` files: nothing. `.claude/hooks/security.sh`: clean (its gitleaks and semgrep printed `mktemp: too few X's` and then reported clean).
- Integration not run: no service changes.

## Beyond the tests
- Doc-comments for each new prop and hook; the one-tree rule in `ChatLayout`'s comments.
- `aria-controls` on ☰ points at the sidebar's `useId`.
- Decision 20 (read state under a covering panel) needs nothing: `MessageList` is untouched.
- Viewport meta `interactive-widget=resizes-content` and `#root` at `100dvh` (Decision 21).

## Departures from the plan
- The image cap is done with a button-level `[&>img]` rule so `max-w-80` stays on the image: an existing test pins that class and I may not touch tests. Same cap.
- The member panel is cleared during wide (and `drawerOpen` likewise), as the red report asked for Decision 17.
- Close button reads "Close" visibly with `aria-label="Close sidebar"`.

## Picked up from earlier reviews
- Test review 2, Decision 17: done as above. Journey arrangement (`is_where_left`): passed, no extra filler needed. The `display:none` risk: the journey's where-she-left-it check passed.
- Plan review 3: the 360 tour writes a DM; the scenario truncates messaging first, nothing to do. Decisions 23 and 24 followed.

## Left for the human
At 360×740 and 390×844 on a real phone: every control reachable and usable (composer row, an admin's header with Members, Settings' fields, sign-in); the composer above the on-screen keyboard; a real rotation with a thread and drafts. The acceptance-reviewer adds sign-in to its check 4 and performs check 3 in Decision 23's order.
