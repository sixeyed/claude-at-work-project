# Federate to an upstream OIDC provider rather than being one

- **Status:** Accepted
- **Date:** 2026-07-28

## Context

Everything downstream of identity in CollabHub has been built and working for
some time: RS256 signing with key rotation, the JWKS endpoint every other service
verifies against, rotating refresh tokens with reuse detection, workspace-scoped
access tokens, and client-credentials service tokens. What was missing was the
part at the very front — establishing who the user actually is.

The MVP stood in a local-only `POST /auth/dev-login` that minted a real token
pair for any email address with no credential at all. It was registered only when
`APP_ENV=local`, and it existed precisely so the rest of the platform had genuine
tokens to verify while this decision stayed open. Register D5 has been sitting on
the question since the design docs were written: does the Auth service act as a
full OpenID Connect provider for first-party clients, or does it only federate to
an upstream identity provider?

The question is load-bearing because it decides how much protocol surface the
team owns forever. It also blocks any deployed environment — nothing can ship
while the only way to sign in is a route that trusts an email address.

The constraints that matter: CollabHub has exactly one first-party client, its
own SPA. There is no third-party integration story, and none is planned. The
target customers are organisations that already run an identity provider and will
expect to plug their own in — that is the normal enterprise expectation, and it
is also what makes SSO a checkbox on procurement forms. The team is small and has
no security specialist.

## Decision

We will federate. The Auth service is an OpenID Connect **relying party** and
never an OpenID Connect provider. It sends the user to an upstream provider,
validates the id_token that comes back, links that identity to a CollabHub
account, and then issues its own tokens exactly as it already did.

Locally, the upstream provider is **Dex** (`ghcr.io/dexidp/dex`), added to the
compose stack with three static accounts so multi-user behaviour — the workspace
switcher, adding a member, changing a role — is exercisable on a laptop. In a
deployed environment Dex is replaced by whatever the organisation already runs.
Nothing in the service changes but configuration.

Two things follow directly and are worth stating because they are the parts most
likely to be undone by accident:

The SPA still gets a CollabHub authorization code, not the provider's. The
callback establishes identity, then mints a short-lived single-use code that the
SPA exchanges at `/auth/token` with PKCE. So there are two independent PKCE
exchanges — ours with the provider, and the SPA's with us. The second is what
makes it safe for the code to travel in a redirect URL where it lands in browser
history.

`dev-login` is **deleted**, not disabled. A credential-less route that exists but
is switched off is a route somebody can misconfigure back into service; one that
was removed is not. The integration tests now drive the real Dex flow, login form
and all.

## Consequences

The protocol surface we own shrinks to the relying-party half, which is perhaps a
fifth of what being a provider would demand. There is no `/authorize`, no client
registry, no consent screen, no OP discovery document, no refresh-token grant for
third parties, and no long tail of OIDC conformance to chase. The parts of OIDC
that are genuinely hard to get right — and dangerous to get wrong — are now
someone else's implementation, reviewed by more people than we could put on it.

Enterprise SSO becomes configuration rather than a project. Adding a customer's
Okta, Entra ID or Keycloak is a new entry in `OIDC_PROVIDERS`, because they are
all the same protocol from our side.

We inherit a hard dependency on the provider being reachable. When it is down,
nobody can sign in. Existing sessions keep working — access tokens verify
statelessly against our own JWKS and refresh does not touch the provider — so an
outage degrades to "no new sign-ins" rather than "nobody can use CollabHub",
which is the right shape but is still a dependency we did not have.

We take on the account-linking problem, which is the genuinely subtle part.
Matching is on `(provider, subject)` first, so a user who changes their email
upstream keeps their account. Falling back to matching on email is a convenience
that becomes an account-takeover path if the provider does not verify addresses,
so it is gated on `email_verified` and refused otherwise. This is the kind of
rule that looks like an edge case and is not.

The public-versus-internal authority split is now a permanent piece of
configuration. An OIDC issuer is an identity, not an address: it is what lands in
`iss` and where the browser is sent, while the back-channel calls need a URL this
process can actually reach. They differ locally and in any cluster whose public
hostname is not its in-cluster service name. Conflating them produces a service
that works from a browser and cannot complete a token exchange — a failure that
looks like a networking problem and is a configuration one.

Local development now depends on a container that must be healthy before anyone
can sign in, and the integration tests script Dex's login form, which couples
them to that page's markup. A Dex upgrade can therefore break the test suite
without breaking the product. This is flagged in `docs/platform/versions.md`, and
the alternative — Dex's `mockCallback` connector — authenticates only one
hard-coded user, which would make the multi-user tests impossible.

Being a provider is not foreclosed. If a third-party integration story ever
arrives, the OP surface can be added alongside federation; nothing here prevents
it. The decision is to not build it speculatively for a single first-party
client.

## Alternatives Considered

### Act as a full OIDC provider, federating upstream for authentication

The most standards-correct option, and the one that ages best if CollabHub ever
gains third-party API clients. It means implementing `/authorize`, an OP
discovery document, a client registry, consent, and the id_token and nonce
machinery — weeks of protocol surface, and protocol surface where mistakes are
security vulnerabilities rather than bugs. All of it to serve one SPA that we
also write. The generality has no consumer, so it is cost without a
corresponding benefit; it can be added later if a real second client appears.

### oauth2-proxy in front of the services

A reverse proxy that completes the OIDC dance and forwards identity headers such
as `X-Forwarded-Email` to the application behind it. It removes the relying-party
code entirely, which is genuinely attractive.

It was rejected on two grounds. First, it solves a problem we do not have: it
exists to put authentication in front of an application that has none, whereas
the Auth service already owns token issuance, account linking and workspace
membership — the proxy would only cover the leg we would then still have to
integrate with. Second, and decisively, trusting injected headers means the
service's security depends on the proxy being unbypassable. Anything that reaches
the service directly authenticates as whoever it claims to be. The chart has no
Ingress and routing is per-environment, so "unbypassable" would be an assumption
made in a place this repository does not control. A misconfiguration would be a
silent, total authentication bypass rather than a visible failure.

### Keep dev-login and defer the decision again

Cheapest in the moment and genuinely tempting, since everything downstream of
identity already worked. Rejected because it blocks every deployed environment
indefinitely, and because the longer a credential-less sign-in route lives in the
codebase the more things quietly grow to depend on it — the tests already did.
Deferring also front-loads no learning: the account-linking and authority-split
problems above were only discovered by building it.

### Local password accounts in the Auth service

Store password hashes ourselves and skip the upstream provider entirely. It is
the least infrastructure for local development, but it means owning password
storage, reset flows, rate limiting, breach response and eventually MFA — all of
the work federation exists to avoid — and it is the opposite of what the target
customers want, since they expect to bring their own identity provider.
