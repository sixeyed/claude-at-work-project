# Deliver the refresh token in an HttpOnly cookie

- **Status:** Accepted
- **Date:** 2026-07-28

## Context

A CollabHub session is two tokens. The access token lives fifteen minutes, is a
Bearer header, and is verified statelessly by every service. The refresh token
lives thirty days, rotates on every use, and is the only thing that can mint new
access tokens. It is therefore the one worth stealing, and the question of where
the browser keeps it has been open in the register as D22 since the design docs
were written, with the note "HttpOnly cookie if same-site allows; avoid
localStorage".

Until now the SPA held it in `sessionStorage`. That was a deliberate placeholder
rather than an answer — the federated sign-in built for D5 needed the token to
survive a full-page redirect to the identity provider and back, which rules out
a variable, and `sessionStorage` was the narrowest thing that worked while the
decision stayed open.

The problem with every in-app option is the same and does not vary between them:
`localStorage`, `sessionStorage` and IndexedDB are all readable by any
JavaScript running on the origin. That is precisely the code an XSS gives an
attacker. `sessionStorage` narrows the window to one tab and one session, which
is a smaller target, not a different kind of target — a single injected script
still walks away with thirty days of access.

The constraint that makes the alternative viable is deployment shape. A cookie
is only useful if the browser will actually send it, and under any sane
anti-CSRF setting that requires the SPA and the API to be **same-site**. Cookies
ignore ports and treat subdomains as the same site, so `localhost:5173` and
`localhost:8001` already qualify, as would `app.collabhub.dev` and
`api.collabhub.dev`, as would a single origin behind one ingress.

## Decision

The refresh token is delivered as a cookie and never appears in a request or
response body.

```
Set-Cookie: collabhub_rt=…; HttpOnly; Secure; SameSite=Strict;
            Path=/api/v1/auth; Max-Age=2592000
```

Each attribute is carrying weight:

**`HttpOnly`** is the decision. The token is never in the JavaScript heap, so
there is nothing for injected script to read — not from `document.cookie`, not
from a response body, not from storage. The SPA cannot see its own refresh
token, which is why `POST /auth/refresh` now takes no request body at all and
`POST /auth/switch-workspace` takes only the workspace to move to.

**`SameSite=Strict`** closes the hole that allowing credentials opens. Once the
browser attaches a credential by itself, any site can try to trigger a renewal
from a victim's browser; `Strict` means no cross-site request carries the cookie,
so there is nothing to forge and no separate anti-CSRF token is needed.

**`Path=/api/v1/auth`** keeps the token away from services that have no use for
it. Messaging, Canvas and Asset never receive it, so none of them can log it.

**`Secure`** keeps it off plaintext connections. Browsers treat `http://localhost`
as a trustworthy origin and accept `Secure` cookies there, so local development
needs no exception — verified in Chrome against the running stack.

**The SPA and the API must be deployed same-site.** This is now a constraint on
deployment topology rather than a preference, and it is the condition the
register's own note attached to this option.

`Access-Control-Allow-Credentials` is turned on in `collabhub-shared`, and the
CORS origin list can no longer be a wildcard — browsers refuse that combination,
which is the right instinct made mandatory.

## Consequences

The XSS exposure that motivated D22 is gone rather than reduced. An attacker who
achieves script execution on the origin can still act as the user *while the page
is open* — they can read the in-memory access token and make requests with it —
but they cannot exfiltrate a thirty-day credential and use it later from
somewhere else. The blast radius shrinks from "persistent account compromise" to
"session-length compromise", which is the meaningful difference.

A stolen refresh token becomes much harder to use even if obtained another way.
The endpoints read the cookie and nothing else, so possession of the value is not
enough; an attacker needs a browser willing to send it, which `SameSite=Strict`
and the path scope both work against.

The SPA gets simpler. It stores nothing at all now except the PKCE verifier
during the seconds of a redirect — verified in a live browser, with
`document.cookie`, `localStorage` and `sessionStorage` all empty on a signed-in
page. `restore()` on page load no longer checks for a stored token; it attempts a
renewal and lets the answer decide, because the SPA genuinely cannot know whether
a session exists until it asks.

We accept a deployment constraint that is easy to violate by accident. Splitting
the SPA and the API across genuinely different registrable domains would stop the
cookie being sent under `Strict`, and the symptom would be "everyone is silently
signed out" rather than an error pointing at the cause. Recovering would mean
`SameSite=None` plus a double-submit anti-CSRF token — a different design, not a
configuration change. This is documented on `auth/cookies.py`, which owns the
constraint.

Non-browser clients now need a cookie jar. In practice this affects only
development tooling: services authenticate with client-credentials service tokens
and never hold refresh tokens, so browsers are the only real consumer.
`scripts/sign-in.py` keeps a jar the way a browser would and grew a
`--refresh-cookie` flag so `api.http` can send a `Cookie` header by hand — a
development affordance that exists because a browser would never reveal the
value.

The tests had to become explicit about whose session they mean. A single httpx
client has one cookie jar, so signing in as a second user would silently
overwrite the first and every multi-user test would quietly assert about whoever
signed in last. `dexflow.finish` now returns the issued cookie and drops it from
the jar, and tests name the session on each request. That is more verbose and
considerably harder to get wrong.

Native or mobile clients, if they ever arrive, will not fit this comfortably.
They can hold cookies, but the idiomatic answer there is an OS keychain, and that
would mean a second delivery mechanism. Not a problem today — there is one
first-party client and it is a browser.

## Alternatives Considered

### Keep `sessionStorage`

What was there. Cheapest, and genuinely narrower than `localStorage` — cleared
when the tab closes, not shared between tabs. Rejected because the exposure is
categorical rather than a matter of degree: any script on the origin can read it,
so an XSS yields a thirty-day credential. The register already said "avoid
localStorage", and the reasoning applies to `sessionStorage` with only the window
of opportunity changed.

### `SameSite=None` with a double-submit anti-CSRF token

Works regardless of where the SPA and API are deployed, which is the one real
advantage. It requires a second, deliberately readable cookie that the SPA echoes
in a header, verified on every state-changing auth route. Rejected for now
because it adds moving parts — and a CSRF control that must be remembered on each
new endpoint — to buy flexibility nothing currently needs. If a deployment ever
genuinely requires cross-site, this is the design to move to.

### Cookie for browsers, token in the body for everything else

Tempting because it would have left `scripts/sign-in.py`, `api.http` and the
tests untouched. Rejected because it settles D22 in name only: a refresh token in
a response body is in the JavaScript heap at the moment of the exchange, which is
exactly the exposure the cookie exists to remove. A control with a documented
bypass is not a control.

### Access token in the cookie as well

Would remove the last token from JavaScript entirely. Rejected because the access
token has to travel to five services as a Bearer header — that is Conventions
§5.1 and the basis of stateless verification — so it must be readable by the code
making those calls. It is also short-lived and re-obtainable, so the exposure it
carries is much smaller.
