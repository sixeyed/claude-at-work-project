# CollabHub SPA

React + TypeScript + Vite. Spec:
[docs/design/06-frontend-spa.md](../../docs/design/06-frontend-spa.md), on top of
[Platform Conventions](../../docs/design/00-platform-conventions.md).

## What is built

**Sign-in**, all the way through the real identity provider: PKCE against Auth,
which federates to Dex locally (register D5). The refresh token is an `HttpOnly`
cookie this code cannot read (D22) — the session restores from it on load and
renews ahead of expiry.

**The workspace switcher.** A token is scoped to one workspace (D2), so
switching is a real token exchange and not a UI filter.

**The chat shell** — `src/features/channels/`: the channel sidebar, create
(public or private), the channel view with its header, the member panel, message
history with infinite scroll, the composer, edit and delete, and the live
connection with typing indicators.

Nothing else in doc 06 §3's tree exists yet: threads, canvas, presence and
assets are all later.

## Rules worth knowing before you change anything here

**TanStack Query owns *all* server state. Zustand owns client state only.**
`src/stores/chat.ts` holds which channel is open, half-typed drafts and the
connection status — and **never a copy of a channel or message list** (register
D24). Two copies of server state diverge, and the bug shows up as a sidebar one
action out of date.

**Query keys lead with the workspace id.** A token is scoped to one workspace,
so a switch reads a *different* cache entry rather than relying on a lifecycle
hook someone can forget to write. See `useChannels.ts`.

**Messaging types are generated, never hand-written** (register D23).
`src/types/messaging.ts` is output — editing it is editing a build artefact:

```bash
uv run python -m messaging.openapi > src/frontend/openapi/messaging.json
cd src/frontend && npm run generate:api
```

**History is a `useInfiniteQuery`, so the cached value is `{ pages, pageParams }`.**
Anything writing into it goes through `upsertMessage` / `removeMessage` in
`useMessages.ts` — setting a bare array breaks the query silently. Those helpers
are **idempotent on the message id and never append**: the sender receives its
own broadcast, and there is no id to skip it by, so an append renders every
message twice in its author's own window. They also **no-op on a channel with
nothing cached**, because writing into an empty key would invent a one-message
history with no cursor that the real history could never replace.

**Newest-first on the wire, oldest-first on screen — and the flip happens
once**, in `useMessages`'s `select`, which copies before reversing because
`Array.reverse` mutates the cached response.

**Tailwind v4 through `@tailwindcss/vite`, with no config files** (register
D26). The theme is `@theme` tokens in `src/index.css`. **Light palette only**,
because there is nowhere to store a theme choice — there is no user-preferences
feature anywhere in the design (D28 🔴). Use the tokens and never a literal
colour: that is what keeps a dark palette cheap if D28 ever lands.

**`data-testid` attributes are part of the contract.** They exist for the
acceptance suite in `tests/bdd/`, where every selector lives in a page object.
Removing one breaks a scenario, not a unit test.

**The server owns validation and this app renders what it says.** No length
checks, no name regexes — a second copy of a rule drifts from the one guarding
the database. `errors.<field>` goes against the input, everything else goes in a
banner.

## Running it

```bash
npm run dev          # frontend work — Vite on :5173 against the Compose services
npm run typecheck    # the gate, with npm run build
npm run build
```

**Never point the BDD suite at `npm run dev`.** StrictMode double-invokes the
effect that restores the session, which spends the rotating refresh token twice
and trips Auth's reuse detection — signing the user out mid-run. That suite runs
against the built frontend container; see the [root README](../../README.md).

`tsconfig.json` is strict, with `verbatimModuleSyntax` — so a type-only import
must say `import type`.

## Configuration

`VITE_AUTH_URL` and `VITE_MESSAGING_URL`, both baked in at build time by Vite
and therefore set as build args in `docker/frontend/Dockerfile`. Everything is
in `.env.example`.
