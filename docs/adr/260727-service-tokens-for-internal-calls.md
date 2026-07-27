# Service tokens for internal service-to-service calls

- **Status:** Accepted
- **Date:** 2026-07-27

## Context

The Worker consumes jobs and produces results that belong to other services. When
it generates image variants it must record them against the asset, but the
platform conventions are explicit that the Worker must not write to another
service's tables — Asset owns `asset_variants`, and sharing a schema across
services is forbidden. The register settled the shape of the write-back as D14:
the Worker calls an internal endpoint on the owning service.

That leaves the part nobody specified. The design docs reference a "service
token" in several places as the thing that authenticates these calls, and never
say what one is, who issues it, how it is scoped, or how it is rotated. Every
service currently authenticates via a single shared dependency that validates a
user's RS256 JWT, and the Worker has no user to present. Jobs are asynchronous
and retried; by the time a thumbnail job runs, the person who uploaded the file
may have logged out hours ago.

There is also a trust boundary worth naming. Internal endpoints do things no user
should be able to do directly — write variant records, mark assets processed. If
the credential that reaches them is the same kind of credential a browser holds,
then a stolen user token reaches them too.

## Decision

We will have the Auth service issue **service tokens**: short-lived RS256 JWTs
signed with the same keys and published through the same JWKS endpoint, so every
service verifies them through the existing code path rather than a second
mechanism.

Service tokens differ from user tokens in three deliberate ways. Their `sub`
identifies the calling service rather than a person (`service:worker`). They
carry an `scp` claim listing granted scopes, such as `assets:write-variants`,
instead of user roles, and they carry no `wsp` claim. Most importantly they use a
distinct audience, `collabhub-internal`, rather than `collabhub`.

That audience split is the point. Because `aud` is already validated on every
request, a user token can never satisfy an internal endpoint and a service token
can never satisfy a user endpoint — the separation is enforced by the
verification that already exists, not by remembering to check something extra.

Services obtain tokens with a client-credentials exchange against Auth, using a
per-service client ID and secret supplied as environment variables, and cache the
result in memory until shortly before expiry. Internal endpoints live under
`/api/v1/internal/`, are not exposed through the public ingress, and are guarded
by a `require_service(scope)` dependency in `collabhub-shared` that sits alongside
`require_user`. No route carries both.

## Consequences

Verification costs nothing new. Services already fetch and cache JWKS and already
validate issuer, audience and expiry, so accepting service tokens is a second
dependency over the same primitives rather than a parallel trust root with its
own key management. Scopes make the blast radius of each internal endpoint
explicit and reviewable, and a compromised Worker credential grants exactly the
operations it was scoped for.

The significant new cost is that Auth becomes a runtime dependency of the Worker.
It was not one before — the Worker read from Redis and wrote to Elasticsearch and
object storage, and needed nobody's permission. Now it needs a token at startup
and roughly every ten minutes thereafter. The mitigation is that jobs are already
retried: if Auth is unreachable the Worker retries with backoff, and an
unacknowledged job is simply reclaimed and re-run later. The failure mode is
delay, not loss. But it does mean an Auth outage now slows background processing,
which is a coupling worth knowing about.

Each service gains a credential to provision and rotate — Sealed Secrets or Vault
on-prem, Key Vault CSI on Azure. Rotation is the real revocation mechanism here:
the token denylist is keyed on `jti` and sized for user sessions, and consulting
it for service tokens buys little when their lifetime is already minutes. A
compromised service credential is handled by rotating the secret, not by
denylisting tokens.

Auditing needs attention. A write arriving with `sub=service:worker` says which
service acted but not which user's action caused it, and that trail matters when
something goes wrong. The originating user ID should be carried in the job
envelope and logged alongside the service identity, so the chain from user action
to background write stays reconstructable.

## Alternatives Considered

### A shared static API key per service pair

A long-lived secret in a header, checked on arrival. Trivially simple and needs
no Auth involvement at all.

Rejected because it is a second authentication mechanism to build, document and
maintain alongside the JWT one, and a weaker one: no expiry, no scopes, and
rotation that requires coordinating restarts across both sides. The simplicity is
real but it is front-loaded, and the operational cost lands later and repeatedly.

### Mutual TLS between services

Strong authentication at the transport layer, with no application-level
credential to leak, and the natural answer if a service mesh is ever adopted.

Rejected for now on cost and fit. Without a mesh, certificate issuance, rotation
and distribution is substantial work for a platform that is not yet built. It
also authenticates the caller without saying what the caller may do, so an
in-band authorization claim would still be needed — meaning mTLS complements this
decision rather than replacing it. Worth revisiting if a mesh arrives.

### Reuse the originating user's token

Carry the access token that triggered the job in the job envelope and have the
Worker present it.

Rejected on two independent grounds. Access tokens live 15 minutes while jobs may
be retried for far longer, so the credential would routinely be expired at the
moment it is needed. And it would place live user credentials in a Redis stream
that is persisted, replayed and inspected during debugging, which is a poor place
for them. The Worker's authority should come from being the Worker, not from
borrowing a person's identity.

### Let the Worker write `asset_variants` directly

The shortest path, and briefly tempting because the Worker already holds a
Postgres connection.

Ruled out by the platform conventions, and rightly. It would couple the Worker to
Asset's schema, meaning an Asset migration could break the Worker silently, and it
would put write logic for a table outside the service that owns it.
