# CollabHub — Auth Service

> Identity, token issuance, and authorization source of truth.
> Read [Platform Conventions](./00-platform-conventions.md) first.

**Status:** Draft · **Runtime:** Python 3.12 / FastAPI (Uvicorn)
**Owns:** users, external identities, roles, workspace membership, tokens
**Depends on:** PostgreSQL (own DB), Redis Cache (R1)

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
- **Authlib** for the OpenID Connect client flow; **python3-saml** (or equivalent) for SAML.
- **PyJWT** (or Authlib's JWT support) for RS256 signing and JWKS generation
  (`cryptography` provides the underlying RSA primitives).
- SQLAlchemy 2.0 (async) + asyncpg for PostgreSQL; Alembic for migrations.
- `redis-py` (`redis.asyncio`) for the R1 denylist + token cache.
- Signing keys: RSA key pair stored as a secret; supports key rotation (multiple `kid`s,
  one active for signing, several valid for verification).

---

## 3. Public Interface (REST)

Base path `/api/v1`. Token endpoints and JWKS are unauthenticated; all others require Bearer.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/auth/dev-login` | none | **Local only.** Sign in as any email with no credential; stands in for the OIDC flow while D5 is open. Registered only when `APP_ENV=local`. |
| GET | `/.well-known/jwks.json` | none | Public verification keys (JWKS). |
| GET | `/.well-known/openid-configuration` | none | OIDC discovery (if acting as OP). |
| GET | `/auth/login/{provider}` | none | Begin external OIDC/SAML login (redirect). |
| GET | `/auth/callback/{provider}` | none | Provider callback; establishes identity, redirects to SPA with auth code. |
| POST | `/auth/token` | none | Exchange auth code (PKCE) for access + refresh tokens. |
| POST | `/auth/refresh` | none | Rotate refresh token → new access + refresh. |
| POST | `/auth/logout` | Bearer | Revoke current token's `jti` + refresh token. |
| GET | `/auth/userinfo` | Bearer | Claims for the current token. |
| GET | `/users/me` | Bearer | Current user profile. |
| PATCH | `/users/me` | Bearer | Update own profile (display name, avatar ref). |
| GET | `/users/{id}` | Bearer | Public profile of a user (name, avatar). |
| GET | `/workspaces/{id}/members` | Bearer (member) | List members + roles. |
| POST | `/workspaces/{id}/members` | Bearer (admin) | Invite/add member. |
| PATCH | `/workspaces/{id}/members/{userId}` | Bearer (admin) | Change role. |
| DELETE | `/workspaces/{id}/members/{userId}` | Bearer (admin) | Remove member. |
| GET | `/workspaces` | Bearer | Workspaces the current user belongs to (for the switcher). |
| POST | `/auth/switch-workspace` | none | Exchange refresh token + target workspace → new token pair scoped to that workspace. |
| POST | `/auth/service-token` | none | Client-credentials grant for internal service tokens (Conventions §5.5). |

The three `/workspaces/{id}/members` write endpoints are in the **fail-closed** set for
denylist checks (Conventions §5.2) — they must return 503 rather than proceed when R1 is
unreachable.

### 3.1 Token endpoint payloads

**Casing:** camelCase throughout, like every other endpoint on the platform
(Conventions §4). Earlier drafts of this section used OAuth 2.0's snake_case field names
for these endpoints only; that carve-out is gone. These endpoints are called by our own
SPA, not by a stock OAuth library, so one casing rule everywhere is worth more than
fidelity to RFC 6749's field spelling.

`POST /auth/token`
```json
// request
{ "grantType": "authorization_code", "code": "...", "codeVerifier": "..." }
// response
{ "accessToken": "ey...", "refreshToken": "def...", "tokenType": "Bearer", "expiresIn": 900 }
```

`POST /auth/dev-login` — **local only**, and the MVP's stand-in for the flow above while
register D5 is open. No credential: any email address gets a session, creating the account,
a workspace it owns, and membership of the shared demo workspace on first use.
```json
// request
{ "email": "ada@example.com", "displayName": "Ada Lovelace" }
// response — same shape as /auth/token
```

`POST /auth/refresh`
```json
// request
{ "refreshToken": "def..." }
// response — same shape as /auth/token; the old refreshToken is now invalid (rotation)
```

`POST /auth/switch-workspace` — the workspace-switch flow (Conventions §5.4). Rotates the
refresh token exactly as `/auth/refresh` does; the only difference is the `wsp` and `roles`
claims on the new access token. Rejects with 403 if the user is not a member of the target.
```json
// request
{ "refreshToken": "def...", "workspaceId": "uuid" }
// response — same shape as /auth/token
```

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
1. SPA hits `/auth/login/{provider}` → 302 to external IdP.
2. IdP redirects to `/auth/callback/{provider}`; service validates, upserts `users` +
   `external_identities`, then redirects to the SPA redirect URI with a short-lived auth code.
3. SPA calls `/auth/token` with the code + PKCE `code_verifier` → access + refresh tokens.

### 5.2 Refresh rotation
On `/auth/refresh`: look up by `token_hash`, ensure not revoked/expired, mint a new pair,
set `rotated_to` and `revoked_at` on the old row (reuse of a rotated token ⇒ revoke the whole
family and 401 — detects token theft).

### 5.3 Token verification (for other services)
Other services do NOT call this service per request. They fetch JWKS and verify locally with
PyJWT/Authlib (Conventions §5). This service only needs to keep JWKS current and maintain the
denylist.

---

## 6. Configuration

Common vars per Conventions §8, plus:

| Var | Notes |
|-----|-------|
| `AUTH_SIGNING_KEY` | PEM RSA private key (secret). Active `kid`. |
| `AUTH_PREVIOUS_KEYS` | Prior public keys still valid for verification (rotation). |
| `AUTH_ACCESS_TOKEN_MINUTES` | Default 15. |
| `AUTH_REFRESH_TOKEN_DAYS` | Default 30. |
| `OIDC_{PROVIDER}_AUTHORITY` / `_CLIENT_ID` / `_CLIENT_SECRET` | Per external IdP. |
| `SAML_{PROVIDER}_METADATA_URL` | Per SAML IdP. |
| `SPA_REDIRECT_URI` | Allowed post-login redirect. |

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
- Acting as a full OIDC OP for first-party clients vs. only federating to an upstream IdP
  (register D5). **Deferred, not decided:** the MVP stands in a local-only `dev-login`
  endpoint so the rest of the platform has real tokens to verify. `external_identities` is
  created and empty, waiting for whichever answer wins.
- ~~Multi-workspace membership and the workspace-switch flow~~ — 🟢 **Decided 2026-07-27
  (register D2).** Many-to-many membership; one workspace per access token; switch via
  `POST /auth/switch-workspace`. See Conventions §5.4 and the
  [ADR](../adr/260727-single-active-workspace-per-token.md).
- Whether SAML is in scope for v1 or deferred.
- Refresh tokens stored hashed in Postgres here; could move to R1 — confirm durability need.
