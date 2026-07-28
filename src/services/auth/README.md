# Auth Service

Identity, token issuance, and the authorization source of truth for CollabHub.

Design: [`docs/design/01-auth-service.md`](../../../docs/design/01-auth-service.md) ·
Platform contract: [`docs/design/00-platform-conventions.md`](../../../docs/design/00-platform-conventions.md)

---

## What it owns

- **User accounts** and their links to upstream identities (`external_identities`).
- **Workspaces and membership**, with roles `owner` / `admin` / `member` / `guest`. The
  `roles` claim on every access token on the platform comes from here.
- **Token issuance** — RS256 access tokens, rotating refresh tokens, and client-credentials
  service tokens for internal calls.
- **The JWKS endpoint** every other service verifies against.

It does **not** own per-resource permissions. Each service enforces its own (Conventions
§5.3); the token establishes identity, workspace, and workspace role, and nothing more.

## What it is not

**Not an OpenID Provider.** Auth is an OIDC *relying party*: it sends the user to an
upstream provider and turns the id_token that comes back into a CollabHub identity. Settled
2026-07-28 — register D5, [ADR](../../../docs/adr/260728-federate-to-an-upstream-oidc-provider.md).

There is deliberately no `/.well-known/openid-configuration`. `/.well-known/jwks.json` is
about CollabHub's own signing keys, not the provider's.

**Not on the request path.** Other services never call this one to validate a token. They
fetch the JWKS, cache it, and verify locally (Conventions §5.1). If that were not true,
stateless auth would have made Auth the busiest thing in the cluster.

**Not a holder of the refresh token, as far as the SPA is concerned.** It is delivered as an
`HttpOnly` cookie (register D22), so no client-side code can read it — see
[The refresh cookie](#the-refresh-cookie).

---

## Running it

Auth needs Postgres, Redis Cache (R1) and Dex — nothing else.

```bash
cp .env.example .env          # from the repo root, if you have not already
docker compose up -d postgres redis-cache dex auth
```

Sign in as `ada@`, `grace@` or `alan@collabhub.dev`, password `collabhub`. Either through
the SPA at <http://localhost:5173>, or from a terminal:

```bash
./scripts/sign-in.py                       # access token + refresh cookie, as JSON
./scripts/sign-in.py grace@collabhub.dev
curl -H "Authorization: Bearer $(./scripts/sign-in.py --access-token)" \
     http://localhost:8001/api/v1/users/me
```

`api.http` is a walkthrough of every endpoint for the VS Code REST Client extension. It
cannot drive the sign-in itself — that is a browser flow with an HTML form — so it starts by
asking you to paste values from `sign-in.py`. `--refresh-cookie` prints the cookie value for
the requests that need a `Cookie` header; a browser would never reveal it, which is the
point of the flag existing only in a dev script.

### Migrations

```bash
cd src/services/auth && alembic upgrade head    # or: python -m auth.migrate
```

Locally the container entrypoint runs them (`RUN_MIGRATIONS=true`). In Kubernetes set that
false and run `python -m auth.migrate` as a pre-upgrade Job.

---

## Signing in

```
GET /auth/login/{provider}?codeChallenge=…&codeChallengeMethod=S256
  ├ R1 auth:login:{state} ← nonce, our PKCE verifier, the SPA's challenge   TTL 300s
  └ 302 → provider

GET /auth/callback/{provider}?code=…&state=…
  ├ R1 GETDEL auth:login:{state}
  ├ exchange the code, verify the id_token (signature, iss, aud, exp, nonce)
  ├ link identity → users + external_identities
  ├ R1 auth:code:{code} ← userId, workspaceId, the SPA's challenge          TTL 60s
  └ 302 → SPA_REDIRECT_URI?code=…

POST /auth/token {grantType, code, codeVerifier}
  ├ accessToken in the body
  └ Set-Cookie: collabhub_rt=… (HttpOnly — see below)
```

Five things here are load-bearing, and each has a test that fails if it is undone.

**Two independent PKCE exchanges** — Auth↔provider and SPA↔Auth. The second is why the
CollabHub authorization code can safely travel in a redirect URL, where it lands in browser
history and referrer headers. Sharing one challenge between the legs would hand the provider
the secret protecting our own code.

**Both R1 keys are single-use**, read with `GETDEL`. One command rather than `GET` then
`DEL`, because two leave a window in which concurrent redemptions both succeed.

**This half fails closed.** The opposite of the token denylist (Conventions §5.2), and
deliberately: failing open on an authorization code would mean issuing a session for a code
nobody can show was ever issued.

**`SPA_REDIRECT_URI` is the only redirect target.** No endpoint accepts a redirect URI from
a request, so there is no open redirect to validate against an allow-list.

**The callback answers with redirects, always** — including on failure. Its caller is a
browser mid-navigation, so errors arrive as `SPA_REDIRECT_URI?error=…` rather than as a
Problem Details document in a bare tab.

### The refresh cookie

**Register D22, settled 2026-07-28** —
[ADR](../../../docs/adr/260728-refresh-token-in-an-httponly-cookie.md).

```
Set-Cookie: collabhub_rt=…; HttpOnly; Secure; SameSite=Strict;
            Path=/api/v1/auth; Max-Age=2592000
```

The refresh token is never in a request or response body. `POST /auth/refresh` and
`POST /auth/logout` take **no body at all**, and `POST /auth/switch-workspace` takes only a
workspace id — the session comes from the cookie, which the browser decides whether to send.

Why each attribute is there:

| | |
|---|---|
| `HttpOnly` | The decision. The token never enters the JS heap, so injected script cannot read it. `sessionStorage` and `localStorage` both can be read by any code on the origin. |
| `SameSite=Strict` | Closes CSRF without a second anti-forgery token. Allowing credentials means the browser attaches the cookie by itself; `Strict` means no cross-site request carries it. |
| `Path=/api/v1/auth` | Messaging, Canvas and Asset never receive it, so none of them can log it. |
| `Secure` | HTTPS only. Browsers accept it on `http://localhost`, so local dev needs no exception. |

**This constrains deployment.** The SPA and the API must be **same-site** — one registrable
domain, or one origin behind a single ingress. Cookies ignore ports and treat subdomains as
the same site, so `localhost:5173`/`localhost:8001` and `app.x.com`/`api.x.com` both
qualify. Split them across genuinely different domains and the cookie silently stops being
sent; the fix would be `SameSite=None` plus a double-submit token, which is a different
design. `auth/cookies.py` owns this constraint.

CORS allows credentials as a result, and the origin list can never be `*` — browsers refuse
that combination.

### Two authorities per provider

An OIDC issuer is an **identity, not an address**.

| | |
|---|---|
| `authority` | The public URL. What lands in `iss`, and where the browser is sent. |
| `internalAuthority` | Where *this process* reaches the provider — discovery, token exchange, JWKS. |

They differ locally because a browser cannot resolve `dex` and the Auth container cannot
resolve its own `localhost`; they differ in any cluster whose public hostname is not its
in-cluster service name. Discovery is fetched over the back channel and its `issuer` checked
against the public authority; the endpoints it advertises carry the public host, so they are
rewritten onto the internal base before use.

Conflating them produces a service that works from a browser and cannot complete a token
exchange — which looks like a networking fault and is a configuration one.

### Account linking

1. `(provider, subject)` matches → that user. Matching on the provider's stable subject
   rather than the email means a user who changes their email upstream keeps their account.
2. No identity, but the email already has an account → link them, **only if the id_token
   asserts `email_verified`**. A provider that lets users set an arbitrary address would
   otherwise make this an account-takeover path.
3. Nobody → provision: the user, a workspace they own, and locally the shared demo
   workspace so two accounts have somewhere to meet.

---

## Rules that are easy to get wrong

- **The workspace comes from the token.** Every member endpoint requires the path workspace
  to *equal* the `wsp` claim, not merely to be one the caller belongs to (Conventions §5.4).
  To administer another workspace, switch token first.
- **Membership writes fail closed** — `require_user_sensitive`, so 503 rather than proceed
  on a token whose revocation cannot be checked (Conventions §5.2). The reads do not.
- **Removing a member revokes their refresh tokens for that workspace.** Without it, removal
  only stops them getting a *new* session while the token they hold keeps working for thirty
  days.
- **The last owner cannot be removed or demoted.** A workspace with no owner has nobody left
  who can grant the role back.
- **`GET /users/{id}` never returns an email**, and only answers for users who share a
  workspace with the caller — otherwise a workspace-scoped token is a directory of every
  tenant.
- **Adding a member is not an invitation.** There is no invitations table, so an unknown
  address is a 404. A real invite flow is an open question.

---

## Tests

```bash
uv run pytest src/services/auth              # from the repo root
uv run pytest src/services/auth -m "not integration"   # no Docker needed
```

Integration tests run **a real Dex in a testcontainer** and drive the genuine redirect flow,
login form and all — a stubbed provider would test our idea of OIDC rather than OIDC.
`tests/dexflow.py` plays the browser.

Two things to know when they break:

- `tests/dexflow.py` parses Dex's login page to find the form action, so a **Dex upgrade can
  break the suite without breaking the product**. `docs/platform/versions.md` says so on the
  Dex entry. The alternative — Dex's `mockCallback` connector — authenticates one hard-coded
  user, which would make the multi-user tests impossible.
- Dex binds a **fixed** host port (15556), not a random one, because the issuer is baked into
  its config and cannot be discovered after startup. It is not 5556, so a running
  `docker compose up` and a test run do not collide.

---

## Layout

```
auth/
  main.py            create_app — wiring, nothing else
  settings.py        every environment variable this service reads
  oidc.py            the relying-party half: discovery, exchange, id_token verification
  loginflow.py       the two single-use R1 keys a login turns on
  pkce.py            verifier / challenge, S256 only
  identities.py      users, workspaces, membership — no HTTP, no tokens
  sessions.py        issue, rotate, revoke
  tokens.py          claim shapes and signing — pure, no I/O
  cookies.py         the refresh cookie and its attributes (register D22)
  keys.py            RS256 signing material and rotation
  models.py          SQLAlchemy, one-to-one with the design doc's tables
  schemas.py         request/response bodies (camelCase on the wire)
  routers/
    federation.py    login → callback → token
    auth.py          refresh, switch-workspace, logout, userinfo, service-token
    users.py         profiles
    workspaces.py    membership
    wellknown.py     JWKS
scripts/sign-in.py   drive a real Dex sign-in from a terminal
api.http             manual walkthrough of every endpoint
```
