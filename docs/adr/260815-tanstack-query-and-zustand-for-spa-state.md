# Split SPA state between TanStack Query and Zustand

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

Register D24 asked which client state manager the SPA should use, framing it as
Zustand versus Redux Toolkit. Until now the question could be deferred: the app
was a sign-in scaffold whose only shared state was the session, held in a
hand-written module store in `lib/auth/session.ts` with a `subscribe`/`snapshot`
pair for `useSyncExternalStore`. Building the chat UI ends that. A channel list
is fetched, cached, shown in two places, invalidated when someone creates a
channel, and — from the next slice — updated by Socket.IO events arriving
outside any React render.

The framing in the register is the part worth challenging. "Zustand vs Redux
Toolkit" treats all client-side state as one problem, but the SPA has two kinds
that behave nothing alike. Channels, messages and memberships are *server*
state: the browser holds a copy of something it does not own, which can be
stale, needs refetching, and has loading and error states as a matter of course.
The active channel id, connection status and per-channel drafts are *client*
state: the server has no opinion about them and they are never stale.

Managing server state in a general-purpose store means hand-writing caching,
deduplication, invalidation and request lifecycle for every resource — which is
how a store fills up with `channelsLoading`, `channelsError` and a reducer per
endpoint. Doc 06 §2 already names TanStack Query for data fetching and Zustand
"(or Redux Toolkit)" for UI state, so the design anticipated the split without
recording it as a decision.

## Decision

We will use **TanStack Query for server state and Zustand for client state**,
and treat the boundary between them as a rule rather than a preference: anything
the server owns lives in the Query cache and nowhere else.

Zustand wins the client-state half on size. The state it holds is a handful of
fields; Redux Toolkit's slices, actions and store configuration are machinery
for a problem this app does not have once Query owns the fetching. Zustand's
store is a hook, so no provider is needed and the existing session module can
keep its `useSyncExternalStore` shape until there is a reason to move it.

The rule has a concrete consequence that is easy to get wrong, so it is written
into `stores/chat.ts`: **no copy of the channel or message list goes in
Zustand.** Socket.IO events write into the Query cache with
`queryClient.setQueryData`. Two copies of server state diverge, and the symptom
is a sidebar one action out of date.

Query keys carry the workspace id — `['channels', workspaceId]`. An access token
is scoped to one workspace (Conventions §5.4), so a cached list belongs to that
workspace and to no other. Doc 06 §4 asks for the cache to be cleared on a
workspace switch; keying by workspace gets the same guarantee structurally,
without a lifecycle hook someone can forget to call, and switching back does not
refetch what is still valid.

## Consequences

Loading and error states come from the library rather than from fields we
maintain, and a create invalidates one query key to refresh every component
reading it. Retry policy is set once: a 4xx is the server's considered answer,
so it is not retried, while a 5xx gets one attempt.

The cost is two state systems in one app, and a boundary that has to be
understood before it can be respected. A developer who has not internalised the
split will reach for the Zustand store to hold a channel list, because that is
what a store is for in most apps. The rule is documented in `stores/chat.ts`
where someone about to break it is most likely to be reading, but documentation
is weaker than a type error and this will need watching in review.

TanStack Query is also a meaningful dependency — around 40 KB — and the app now
carries both it and Zustand. For an app of this eventual size that is
proportionate, but it is real weight added to a bundle that was previously three
runtime dependencies.

Workspace-keyed cache entries accumulate for as long as a session lasts. Query's
default garbage collection clears unused entries after five minutes, so this is
bounded, but a user switching between many workspaces holds more in memory than
one who does not.

## Alternatives Considered

### Redux Toolkit with RTK Query

The strongest alternative, and not by much: RTK Query solves the same server
state problem as TanStack Query and would have covered both halves with one
library, which is a genuine simplification. It loses on fit rather than
capability. Adopting it means adopting the Redux store, the provider, and slice
conventions for the small amount of client state that actually exists, and the
existing `lib/auth` session store would sit awkwardly outside it or need
rewriting. If the client state grows to the point where Zustand's lack of
structure hurts — many interdependent slices, or a need for time-travel
debugging — this is the decision to revisit.

### Zustand alone, with hand-written fetching

Keeps the dependency count down and the mental model to one store. Rejected
because it means writing caching, deduplication, invalidation and request
lifecycle by hand for every resource. That code is not hard, it is just endless,
and it is where staleness bugs live — the ones where two components fetch the
same list and disagree about it.

### Keep the hand-written module store and add to it

The session store already works and needs no library at all. It is fine for one
value that changes rarely, and it does not extend: it has no cache, no
invalidation, and no request lifecycle, so every one of those would be built on
top by hand. It stays as it is for the session specifically, but it is not the
answer for chat.
