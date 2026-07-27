# Scope each access token to a single active workspace

- **Status:** Accepted
- **Date:** 2026-07-27

## Context

CollabHub is a multi-workspace product. A user will routinely belong to several
workspaces — their own company, a client's, a side project — and expects to move
between them the way they would in Slack. The design docs assumed a single `wsp`
claim on the access token without ever confirming that users belong to more than
one workspace, or how switching would work. It has sat in the decisions register
as D2, flagged as cross-cutting, because it shapes the token and therefore every
authorization check in every service.

The constraint that makes this decision load-bearing is that authorization here
is stateless. Services verify RS256 JWTs against cached JWKS and never call the
Auth service per request, and they must not read another service's membership
tables. Whatever a service needs in order to answer "is this user allowed to do
this here?" has to be in the token or in that service's own database. So the
token's shape is not a detail — it is the interface every authorization check
programs against, and it is expensive to change once five services depend on it.

Access tokens live 15 minutes; refresh tokens live 30 days and rotate on each
use, with reuse of a rotated token treated as theft.

## Decision

We will model workspace membership as many-to-many, and scope each access token
to exactly one active workspace, named in the `wsp` claim. The `roles` claim
carries the user's role in that workspace only.

Refresh tokens are not workspace-scoped. Switching workspaces is an explicit
exchange: the SPA presents its refresh token along with the target workspace ID
and receives a new access token carrying the new `wsp`. This reuses the existing
rotating-refresh machinery rather than introducing a second credential type.

The decisive argument is that every authorization check in the system gets to
assume, without branching, that there is exactly one workspace in play. A token
carrying several workspaces would push the question "which workspace is this
request about?" into every handler in every service, and that question has to be
answered correctly every single time or it becomes a tenancy leak. Narrowing the
token removes an entire category of bug at the cost of a round trip on an action
users take a few times a day.

## Consequences

Authorization code stays simple: a service reads `wsp`, checks its own tables for
resource-level permission, and is done. Tokens stay small and bounded regardless
of how many workspaces a user accumulates, which matters because the token rides
on every REST call and every Socket.IO handshake.

Revocation gets a useful property almost for free. Removing someone from a
workspace stops mattering after at most 15 minutes without touching the denylist,
because their next token simply won't be issued for that workspace.

The costs are real and worth stating plainly. Switching workspaces is a round
trip to Auth, and the SPA has to treat it as a genuine state transition — cancel
in-flight requests, drop cached query data for the old workspace, and tear down
and re-establish the `/messaging` and `/canvas` Socket.IO connections, since a
connection authenticated for one workspace must not continue serving another.
Getting that teardown wrong is the most likely source of bugs from this decision,
and it is worth an explicit test.

Any cross-workspace view — unified notifications, search across everything a user
can see, an "all unreads" badge — cannot be served by one token. It needs either a
fan-out of per-workspace requests from the client or a dedicated aggregate
endpoint with its own authorization story. If such a feature becomes central to
the product rather than peripheral, this decision is the one to revisit first.

Finally, the refresh token is now broader in scope than any access token minted
from it: it can produce tokens for any workspace the user belongs to. Rotation
and reuse detection already bound that exposure, but it does mean refresh token
handling in the SPA deserves the care the design docs already call for — in
memory or an HttpOnly cookie, never `localStorage`.

## Alternatives Considered

### All workspaces in the token

Carry an array of workspace IDs, or a map of workspace to role, and let the
request indicate which one it concerns. This removes the switch round trip and
makes cross-workspace views trivial.

It loses on three counts. The token grows without bound as membership grows, on a
credential sent with every request and every socket handshake. Every
authorization check must first resolve which of the listed workspaces applies,
turning a lookup into a branch that must be right everywhere. And removing a user
from one workspace no longer expires naturally — the token still asserts the
membership, so you are forced onto the denylist for something that should have
been a non-event.

### Identity-only token, workspace resolved per request

Keep workspace out of the token entirely and have each service resolve
membership from the workspace ID in the URL or a header. Conceptually the
cleanest separation.

It is incompatible with the platform's stateless authorization rule. The service
would have to call Auth on every request or read Auth's membership tables, and
the conventions forbid both. Caching membership per service reintroduces the same
staleness problem in five places instead of one.

### A separate refresh token per workspace

Issue refresh tokens that are themselves workspace-scoped, giving stronger
isolation if one is stolen.

Rejected as a poor trade. The SPA would have to store and rotate a growing set of
long-lived credentials, and the rotating-family theft detection — which is one of
the better properties of the current design — becomes considerably harder to
reason about when there are several concurrent families per user. The isolation
gained does not justify multiplying the most sensitive credential in the system.
