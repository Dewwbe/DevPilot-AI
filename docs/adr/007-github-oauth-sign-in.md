# ADR-007: Sign in with GitHub (OAuth 2.0) and signed session cookies

**Status:** Accepted

## Context
Until now the dashboard had no real authentication: HTTP basic auth at the proxy, and the reviewer
name on approvals was whatever the client sent. Reviewer identity is central to the product's
"a human approves" promise, so it has to be real. Users already have GitHub accounts, and the app is
about GitHub repositories.

## Decision
Authenticate with **GitHub's OAuth 2.0 authorization-code flow**, implemented in the API:
- No scopes are requested; the access token is used once to read the public profile and is not stored.
- A signed, timed `state` cookie protects the redirect (CSRF); the session is a signed
  (`itsdangerous`), HttpOnly, `SameSite=Lax` cookie with a 12-hour lifetime, `Secure` over HTTPS.
- State-changing calls also require an `X-Requested-With: devpilot` header.
- An optional allow-list of GitHub logins restricts who may sign in.
- When the OAuth variables are unset, authentication is **off** and the app behaves as before, so
  local development and the cheap demo stack keep working.
- With sign-in on, the approval endpoint uses the session's login as the reviewer and ignores any
  client-supplied name; audit events record that login.

## Alternatives considered
- **A hosted identity provider (Cognito, Auth0):** more features (MFA, orgs) but another service to
  run and pay for; GitHub login is enough for a developer tool.
- **A reverse-proxy auth layer (oauth2-proxy):** keeps auth out of the app, but then the app cannot
  know the reviewer without trusting forwarded headers, and local mode needs extra moving parts.
- **Server-side sessions in Redis/Postgres:** allows revocation, but needs storage and cleanup.
  Signed cookies are stateless; the cost is that a session cannot be revoked before it expires
  (rotating `DEVPILOT_SESSION_SECRET` signs everyone out).
- **JWTs in local storage:** exposed to XSS; HttpOnly cookies are safer.

## Consequences
- A GitHub OAuth App (one per environment) and three secrets must be provisioned.
- The callback URL is fixed per OAuth App, so a stable URL is required; the single-task ECS stack,
  whose IP changes on restart, is unsuitable until it has an ALB or domain.
- There is one shared workspace: any allowed user sees all repositories and diagnoses. Per-user or
  per-organisation access control is future work.
- Closes the authentication gap recorded in SAFETY.md (G4).
