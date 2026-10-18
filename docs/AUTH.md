# Sign in with GitHub (OAuth 2.0)

DevPilot can require every user to sign in with their GitHub account. When it is on, the dashboard
and API need a session, the reviewer on every approval is the real signed-in user, and the audit
trail records real identities.

It is **off by default** so local development stays frictionless: with no OAuth settings the
sidebar says "Sign-in is off (local mode)" and everything is open.

## How it works
1. The user clicks **Continue with GitHub**. DevPilot redirects to GitHub with a one-time `state`
   value (kept in a short-lived, signed, HttpOnly cookie) to stop cross-site request forgery.
2. GitHub sends the user back to `/api/auth/callback?code=...&state=...`.
3. The server checks `state`, exchanges the `code` for an access token (server to server, using the
   client secret), reads the user's profile, and checks the optional allow-list.
4. It sets a signed, HttpOnly, `SameSite=Lax` session cookie (`Secure` over HTTPS) valid for 12
   hours. The GitHub token is used once and **never stored**.

DevPilot requests **no scopes**: it only reads your public profile (login, name, avatar). It cannot
see or change your repositories through this login. Repository access uses separate credentials
(`DEVPILOT_GITHUB_TOKEN` to read logs, the GitHub App to open PRs).

Every state-changing API call must also carry an `X-Requested-With: devpilot` header, which the
dashboard adds and a cross-site form cannot.

## Set it up

### 1. Create a GitHub OAuth App
GitHub > **Settings** > **Developer settings** > **OAuth Apps** > **New OAuth App**.

| Field | Value |
|---|---|
| Application name | `DevPilot AI` |
| Homepage URL | where the app lives, e.g. `http://localhost:8080` or `https://devpilot.example.com` |
| Authorization callback URL | `<homepage>/api/auth/callback` |

The callback URL must match exactly where users reach the app:

| Where you run it | Callback URL |
|---|---|
| Local Docker Compose | `http://localhost:8080/api/auth/callback` |
| VM behind Caddy | `https://<your domain>/api/auth/callback` |
| Kubernetes | `https://<ingress host>/api/auth/callback` |

An OAuth App has **one** callback URL. Create a separate OAuth App per environment (local, prod)
instead of reusing one. Then click **Generate a new client secret** and copy it once.

### 2. Configure DevPilot
Set these (all three of the first are needed to turn sign-in on):

| Variable | Meaning |
|---|---|
| `DEVPILOT_GITHUB_OAUTH_CLIENT_ID` | From the OAuth App |
| `DEVPILOT_GITHUB_OAUTH_CLIENT_SECRET` | From the OAuth App (keep secret) |
| `DEVPILOT_SESSION_SECRET` | Long random string that signs cookies: `openssl rand -hex 32`. Changing it signs everyone out |
| `DEVPILOT_ALLOWED_GITHUB_USERS` | Optional. Comma-separated GitHub logins. Empty means any GitHub account can sign in |
| `DEVPILOT_PUBLIC_BASE_URL` | Optional. Public origin, e.g. `https://devpilot.example.com`. Needed behind a load balancer that does not forward the host; otherwise it is detected |

**Local (`.env`):**
```
DEVPILOT_GITHUB_OAUTH_CLIENT_ID=Iv1.xxxxxxxx
DEVPILOT_GITHUB_OAUTH_CLIENT_SECRET=xxxxxxxx
DEVPILOT_SESSION_SECRET=<openssl rand -hex 32>
DEVPILOT_ALLOWED_GITHUB_USERS=your-github-login
```
then `docker compose up -d --force-recreate api`, and open http://localhost:8080.

**VM:** put the same variables in `/opt/devpilot/.env`, then redeploy. The Caddy basic-auth block is
no longer needed once sign-in is on; delete it from `deploy/vm/Caddyfile` (the `/api/auth/*` paths
are already public so the callback works).

**Kubernetes:** add `github_oauth_client_id` and `github_oauth_client_secret` to the Secrets Manager
JSON (Terraform seeds a random `session_secret`), then upgrade the chart with
`--set secrets.oauth.enabled=true --set ingress.basicAuth.enabled=false`.

**ECS:** set `github_oauth_client_id`, `github_oauth_client_secret`, `session_secret` and
`public_base_url` in `terraform.tfvars`. This needs a **stable URL**: the single-task stack's public
IP changes whenever the task restarts, which would break the callback. Put an ALB (and ideally a
domain with HTTPS) in front first.

### 3. Who should be allowed in?
With `DEVPILOT_ALLOWED_GITHUB_USERS` empty, **any GitHub user** who finds the URL can sign in and
use the app, including spending your Claude and GitHub API quota. For anything public, set the
allow-list (or keep the Anthropic spend limit low).

All signed-in users share one workspace: there are no per-user or per-organisation permissions yet.

## Troubleshooting

| Symptom | Cause |
|---|---|
| GitHub shows "redirect_uri is not associated with this application" | The callback URL in the OAuth App does not match exactly (scheme, host, port, path). Behind a proxy set `DEVPILOT_PUBLIC_BASE_URL` |
| Back on the sign-in page with "did not complete" | Wrong client secret, or GitHub could not be reached. Check `docker compose logs api` for `oauth_failed` |
| "not on this deployment's allow-list" | Your login is not in `DEVPILOT_ALLOWED_GITHUB_USERS` (case-insensitive) |
| Signed out after a restart or redeploy | `DEVPILOT_SESSION_SECRET` changed. Keep it stable |
| Writes fail with 403 "Missing X-Requested-With" | A script calling the API with a session cookie; add the `X-Requested-With: devpilot` header |
| Signed in but cookie not kept over HTTPS | Proxy not sending `X-Forwarded-Proto`; set `DEVPILOT_PUBLIC_BASE_URL=https://...` |

Tests: `backend/tests/test_auth.py` covers the full flow, CSRF state, forged and expired cookies, the
allow-list, and reviewer identity.
