# CollabHub — Auth Service

> Identity, token issuance, and authorization source of truth.
> Read [Platform Conventions](./00-platform-conventions.md) first.

**Status:** Built · **Runtime:** Python 3.12 / FastAPI (Uvicorn)
**Owns:** users, external identities, roles, workspace membership, tokens
**Depends on:** PostgreSQL (own DB), Redis Cache (R1), an upstream OIDC provider (Dex locally)

---

## 1. Purpose & Responsibilities

The Auth Service is the identity provider and authorization source of truth for CollabHub.

**Owns:**
- User accounts and profiles.
- Federation with external identity providers via **OpenID Connect** (internal SSO) and
  optionally **SAML 2.0** (enterprise federation).
- Issuance, refresh, and revocation of CollabHub access/refresh tokens (JWTs).
- The JWKS endpoint that all other services use to verify tokens.
- Workspace membership and workspace-level roles (`owner`/`admin`/`member`/`guest`).

**Does NOT own:**
- Per-resource permissions (each service owns its own — see Conventions §5.3).
- Sessions for real-time connections (services validate tokens themselves).

---

## 2. Runtime & Dependencies

- FastAPI routers (Uvicorn ASGI server).
- **`httpx` + PyJWT** for the OpenID Connect relying-party flow — discovery, the token
  exchange, and id_token verification against the provider's JWKS. Earlier drafts named
  **Authlib**; it was not used. The relying-party half is a discovery fetch, a form POST and a
  JWT verification, and PyJWT plus the JWKS client already in `collabhub-shared` cover all
  three — adding a second JWT library to the image bought nothing. Reconsider if SAML lands
  (register D6), which is a genuinely different protocol.
- **PyJWT** for RS256 signing and JWKS generation (`cryptography` provides the underlying RSA
  primitives).
- SQLAlchemy 2.0 (async) + asyncpg for PostgreSQL; Alembic for migrations.
- `redis-py` (`redis.asyncio`) for the R1 denylist + token cache.
- Signing keys: RSA key pair stored as a secret; supports key rotation (multiple `kid`s,
  one active for signing, several valid for verification).

---

## 3. Public Interface (REST)

Base path `/api/v1`. Token endpoints and JWKS are unauthenticated; all others require Bearer.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/.well-known/jwks.json` | none | Public verification keys (JWKS). |
| GET | `/auth/login/{provider}` | none | Begin external OIDC login (redirect). Requires `?codeChallenge=` (S256). |
| GET | `/auth/callback/{provider}` | none | Provider callback; establishes identity, redirects to SPA with auth code. |
| POST | `/auth/token` | none | Exchange auth code (PKCE) for an access token + refresh cookie. |
| POST | `/auth/refresh` | cookie | Rotate the refresh cookie → new access token. No body. |
| POST | `/auth/logout` | Bearer | Revoke the `jti` and the cookie's refresh token; clear the cookie. |
| GET | `/auth/userinfo` | Bearer | Claims for the current token. |
| GET | `/users/me` | Bearer | Current user profile. |
| PATCH | `/users/me` | Bearer | Update own profile (display name, avatar ref). |
| GET | `/users/{id}` | Bearer | Public profile of a user (name, avatar). |
| GET | `/workspaces/{id}/members` | Bearer (member) | List members + roles. |
| POST | `/workspaces/{id}/members` | Bearer (admin) | Invite/add member. |
| PATCH | `/workspaces/{id}/members/{userId}` | Bearer (admin) | Change role. |
| DELETE | `/workspaces/{id}/members/{userId}` | Bearer (admin) | Remove member. |
| GET | `/workspaces` | Bearer | Workspaces the current user belongs to (for the switcher). |
| POST | `/auth/switch-workspace` | cookie | Refresh cookie + target workspace → new token scoped to that workspace. |
| POST | `/auth/service-token` | none | Client-credentials grant for internal service tokens (Conventions §5.5). |

There is no `/.well-known/openid-configuration`. Auth is a relying party, never an OpenID
Provider (register D5), so publishing OP discovery would advertise endpoints that do not
exist.

The three `/workspaces/{id}/members` write endpoints are in the **fail-closed** set for
denylist checks (Conventions §5.2) — they return 503 rather than proceed when R1 is
unreachable. All four member endpoints require the path workspace to *equal* the token's
`wsp` claim: Conventions §5.4 says authorization never takes a workspace identifier from
the request in place of the claim, and with a workspace in the path the strictest reading is
the only safe one. `GET /users/{id}` is likewise restricted to users who share a workspace
with the caller, so a workspace-scoped token is not a directory of the whole installation.

`GET /workspaces/{id}/members` is cursor-paginated (Conventions §4.1); `GET /workspaces` is
not, because a user's own memberships are a bounded list.

### 3.1 Token endpoint payloads

**Casing:** camelCase throughout, like every other endpoint on the platform
(Conventions §4). Earlier drafts of this section used OAuth 2.0's snake_case field names
for these endpoints only; that carve-out is gone. These endpoints are called by our own
SPA, not by a stock OAuth library, so one casing rule everywhere is worth more than
fidelity to RFC 6749's field spelling.

**The refresh token is never in a body.** Decided 2026-07-28 (register D22) — it is
delivered as a cookie the browser's JavaScript cannot read, so no request or response below
carries one. See §5.4 and the [ADR](../adr/260728-refresh-token-in-an-httponly-cookie.md).

`POST /auth/token`
```json
// request
{ "grantType": "authorization_code", "code": "...", "codeVerifier": "..." }
// response — plus Set-Cookie: collabhub_rt=…; HttpOnly; Secure; SameSite=Strict
{ "accessToken": "ey...", "tokenType": "Bearer", "expiresIn": 900 }
```

`GET /auth/login/{provider}?codeChallenge=…&codeChallengeMethod=S256` — 302 to the provider.
PKCE is mandatory and `S256` is the only accepted method; RFC 7636 also permits `plain`,
where the challenge *is* the verifier and proves nothing, so accepting it would only add a
way to disable the protection from the query string.

`GET /auth/callback/{provider}` — the provider returns here. Answers with a redirect in
every case, success or failure, because the caller is a browser mid-navigation rather than
the SPA's fetch layer: a Problem Details document in a bare tab helps nobody. Failures
arrive as `SPA_REDIRECT_URI?error=…` with one of `access_denied`, `invalid_state`,
`invalid_request`, `email_not_verified`, `account_not_found`, `no_workspace` or
`temporarily_unavailable`.

`POST /auth/refresh` — **no request body.** The only session it can renew is the one the
browser holds a cookie for, so there is nothing to send. The response is the same shape as
`/auth/token`, with a rotated cookie; the old one is now invalid.

`POST /auth/switch-workspace` — the workspace-switch flow (Conventions §5.4). Rotates the
refresh cookie exactly as `/auth/refresh` does; the only difference is the `wsp` and `roles`
claims on the new access token. Rejects with 403 if the user is not a member of the target.
```json
// request — the session comes from the cookie, never the body
{ "workspaceId": "uuid" }
// response — same shape as /auth/token
```

`POST /auth/logout` — no body either. Revokes the access token's `jti` into the denylist,
revokes the refresh token the cookie carries, and clears the cookie.

`POST /auth/service-token` — internal callers only; not exposed through the public ingress.
Issues a short-lived token with `aud: collabhub-internal` and the scopes granted to that
client (Conventions §5.5).
```json
// request
{ "grantType": "client_credentials", "clientId": "worker", "clientSecret": "..." }
// response
{ "accessToken": "ey...", "tokenType": "Bearer", "expiresIn": 600 }
```

The client registry itself is configuration, not API, so it stays snake_case inside
`AUTH_SERVICE_CLIENTS` along with the rest of the environment (Conventions §8).

Access-token claims follow Conventions §5.1. The Auth Service is the only issuer.

---

## 4. Data Model (PostgreSQL)

```sql
CREATE TABLE users (
    id            uuid PRIMARY KEY,
    email         citext NOT NULL UNIQUE,
    display_name  text NOT NULL,
    avatar_asset  uuid NULL,                 -- references Asset service id (no FK, cross-service)
    status        text NOT NULL DEFAULT 'active',  -- active | suspended | deactivated
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz NULL,
    version       integer NOT NULL DEFAULT 0
);

-- Links a user to an external IdP identity (one row per provider).
CREATE TABLE external_identities (
    id            uuid PRIMARY KEY,
    user_id       uuid NOT NULL REFERENCES users(id),
    provider      text NOT NULL,             -- 'oidc:acme' | 'saml:corp'
    subject       text NOT NULL,             -- the IdP's sub / NameID
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, subject)
);

CREATE TABLE workspaces (
    id            uuid PRIMARY KEY,
    name          text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workspace_members (
    workspace_id  uuid NOT NULL REFERENCES workspaces(id),
    user_id       uuid NOT NULL REFERENCES users(id),
    role          text NOT NULL,             -- owner | admin | member | guest
    joined_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

-- Refresh tokens are persisted (rotation + revocation). Access tokens are NOT stored.
CREATE TABLE refresh_tokens (
    id            uuid PRIMARY KEY,          -- the token's jti family root
    user_id       uuid NOT NULL REFERENCES users(id),
    workspace_id  uuid NOT NULL REFERENCES workspaces(id),  -- workspace this session is currently in
    token_hash    bytea NOT NULL,            -- SHA-256 of the opaque refresh token
    issued_at     timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    rotated_to    uuid NULL REFERENCES refresh_tokens(id),  -- set when rotated
    revoked_at    timestamptz NULL
);
CREATE INDEX ix_refresh_user ON refresh_tokens (user_id) WHERE revoked_at IS NULL;
```

SQLAlchemy models map one-to-one to these tables; Alembic owns the migration history.

`refresh_tokens.workspace_id` was added during implementation and is not in the original
table above. Refresh tokens are not workspace-*scoped* — the holder may switch at any time
(Conventions §5.4) — but the row has to remember which workspace the session was last using.
Without it, `POST /auth/refresh` has nothing to go on and every renewal would silently drop
the user back into their default workspace, so a workspace switch would survive only as long
as one access token.

### 4.1 Redis (R1) usage
- `auth:revoked:{jti}` → `"1"`, TTL = remaining access-token lifetime. Written on logout.
- `auth:userinfo:{userId}` → cached profile blob, short TTL, to speed up `/userinfo`.

---

## 5. Internal Design

### 5.1 Login flow (OIDC, PKCE)

**Decided 2026-07-28 (register D5) — see
[ADR](../adr/260728-federate-to-an-upstream-oidc-provider.md).** Auth federates to an
upstream provider and is never an OpenID Provider itself. Dex locally; a customer's own IdP
elsewhere.

1. SPA generates a PKCE verifier and calls `/auth/login/{provider}` with its challenge.
   Auth writes `auth:login:{state}` to R1 — nonce, *its own* PKCE verifier, and the SPA's
   challenge — then 302s to the provider.
2. Provider redirects to `/auth/callback/{provider}`. Auth consumes the state, exchanges the
   code, and verifies the id_token: signature against the provider's JWKS, `iss`, `aud`,
   expiry, and `nonce`. It upserts `users` + `external_identities`, writes
   `auth:code:{code}` to R1, and redirects to `SPA_REDIRECT_URI?code=…`.
3. SPA calls `/auth/token` with the code + its `codeVerifier` → access + refresh tokens.

**Two independent PKCE exchanges**, and they must not be conflated: Auth↔provider, and
SPA↔Auth. The second is what makes the CollabHub authorization code safe to carry in a
redirect URL, where it lands in browser history and referrer headers — without it, anything
that can read the code can spend it.

**Both R1 keys are single-use and read with `GETDEL`.** One command, not `GET` then `DEL`,
because two commands leave a window in which concurrent redemptions both succeed. A replayed
`state` or captured code therefore finds nothing.

**This half fails closed**, unlike the denylist (Conventions §5.2). Failing open on an
authorization code would mean issuing a session for a code nobody can show was ever issued;
a login that errors is a login the user retries.

**Providers carry two authorities.** An OIDC issuer is an *identity*, not an address: the
`authority` is what appears in `iss` and where the browser is sent, while
`internalAuthority` is where this process reaches the provider for discovery, the token
exchange and JWKS. They differ locally — a browser cannot resolve `dex`, and the container
cannot resolve its own `localhost` — and in any cluster whose public hostname is not its
in-cluster service name. Discovery is fetched over the back channel, its `issuer` checked
against the public authority, and the endpoints it advertises (which the provider derives
from its issuer, so they carry the public host) are rewritten onto the internal base.

**Account linking.** Match `(provider, subject)` first, so a user who changes their email
upstream keeps their account. If there is no such identity but the email already has an
account, link the two **only when the id_token asserts `email_verified`** — a provider that
lets users set an arbitrary address would otherwise make this an account-takeover path.
Otherwise provision: a new user, a workspace they own, and (locally only) the shared demo
workspace.

### 5.2 Refresh rotation
On `/auth/refresh`: look up by `token_hash`, ensure not revoked/expired, mint a new pair,
set `rotated_to` and `revoked_at` on the old row (reuse of a rotated token ⇒ revoke the whole
family and 401 — detects token theft).

### 5.3 Token verification (for other services)
Other services do NOT call this service per request. They fetch JWKS and verify locally with
PyJWT/Authlib (Conventions §5). This service only needs to keep JWKS current and maintain the
denylist.

### 5.4 The refresh cookie

**Decided 2026-07-28 (register D22) — see
[ADR](../adr/260728-refresh-token-in-an-httponly-cookie.md).**

```
Set-Cookie: collabhub_rt=…; HttpOnly; Secure; SameSite=Strict;
            Path=/api/v1/auth; Max-Age=2592000
```

The refresh token is the long-lived half of a session, so it is the half worth stealing. It
is delivered as a cookie and **never appears in a request or response body**: a token that
never enters the JavaScript heap cannot be read by injected script. `localStorage` and
`sessionStorage` are both readable by any code on the origin, which is exactly what an XSS
provides.

Each attribute is load-bearing:

- **`HttpOnly`** — the decision itself. The SPA cannot read its own refresh token, which is
  why `/auth/refresh` and `/auth/logout` take no body and `/auth/switch-workspace` takes
  only a workspace id.
- **`SameSite=Strict`** — closes CSRF without a separate anti-forgery token. Once the
  browser attaches a credential by itself, any site could try to trigger a renewal; under
  `Strict` no cross-site request carries the cookie at all.
- **`Path=/api/v1/auth`** — Messaging, Canvas and Asset never receive it, so none of them
  can log it.
- **`Secure`** — HTTPS only. Browsers accept it on `http://localhost`, so local development
  needs no exception.

**This constrains deployment: the SPA and the API must be same-site** — one registrable
domain, or one origin behind a single ingress. Cookies ignore ports and treat subdomains as
the same site, so `localhost:5173` / `localhost:8001` and
`app.example.com` / `api.example.com` both qualify. Splitting them across genuinely
different domains would silently stop the cookie being sent, and would need `SameSite=None`
plus a double-submit anti-CSRF token — a different design, not a config change.

CORS therefore allows credentials (`shared/cors.py`), and the origin list can no longer be a
wildcard; browsers refuse that combination outright.

---

## 6. Configuration

Common vars per Conventions §8, plus:

| Var | Notes |
|-----|-------|
| `AUTH_SIGNING_KEY` | PEM RSA private key (secret). Active `kid`. |
| `AUTH_PREVIOUS_KEYS` | Prior public keys still valid for verification (rotation). |
| `AUTH_ACCESS_TOKEN_MINUTES` | Default 15. |
| `AUTH_REFRESH_TOKEN_DAYS` | Default 30. |
| `OIDC_PROVIDERS` | JSON array of upstream providers: `name`, `authority`, `internalAuthority`, `clientId`, `clientSecret`, `scopes`. Replaces the `OIDC_{PROVIDER}_AUTHORITY` form this table first specified — pydantic-settings cannot discover unknown variable prefixes without a custom settings source, and `AUTH_SERVICE_CLIENTS` already uses this shape. |
| `AUTH_LOGIN_STATE_TTL_SECONDS` | Default 300. How long a half-finished login may sit in R1. |
| `AUTH_CODE_TTL_SECONDS` | Default 60. How long the SPA has to spend its authorization code. |
| `SAML_{PROVIDER}_METADATA_URL` | Per SAML IdP. SAML is undecided (register D6). |
| `SPA_REDIRECT_URI` | The **only** post-login redirect target. Never taken from a request, so there is no open redirect to validate against a list. |
| `AUTH_COOKIE_SECURE` | Default true, everywhere. Only reason to disable is a browser that refuses `Secure` on `http://localhost`; doing so in a deployed environment puts the session token on the wire in clear. |
| `CORS_ALLOWED_ORIGINS` | Browser origins allowed to call this service. Empty installs no CORS middleware at all, which is right when the SPA and API share an origin behind one ingress. Never `*`. |

---

## 7. Cross-Cutting
Error envelope, health checks, observability, logging per Conventions §4.2, §9, §10.
Emit metric `auth_tokens_issued_total`, `auth_logins_total{provider}`, `auth_refresh_reuse_total`.

---

## 8. Non-Functional & Limits
- Token issuance p99 < 100 ms.
- JWKS cacheable (`Cache-Control`), so verification scales without hitting this service.
- Rate-limit `/auth/token` and `/auth/refresh` per IP + per user.

---

## 9. Open Decisions
- ~~Acting as a full OIDC OP for first-party clients vs. only federating to an upstream
  IdP~~ — 🟢 **Decided 2026-07-28 (register D5).** Federate only; Auth is a relying party and
  never a provider. Dex is the local upstream. `dev-login` is deleted, not disabled. See
  §5.1 and the [ADR](../adr/260728-federate-to-an-upstream-oidc-provider.md).
- **Inviting someone who has no account.** `POST /workspaces/{id}/members` adds an *existing*
  user and 404s on an unknown address, because there is no invitations table in §4. A real
  invite flow needs a table, a delivery channel and an expiry policy — not something to
  imply from an endpoint. Needs a register entry.
- ~~Multi-workspace membership and the workspace-switch flow~~ — 🟢 **Decided 2026-07-27
  (register D2).** Many-to-many membership; one workspace per access token; switch via
  `POST /auth/switch-workspace`. See Conventions §5.4 and the
  [ADR](../adr/260727-single-active-workspace-per-token.md).
- Whether SAML is in scope for v1 or deferred.
- Refresh tokens stored hashed in Postgres here; could move to R1 — confirm durability need.
