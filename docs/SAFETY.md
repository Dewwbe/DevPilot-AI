# Safety and Threat Model (living document)

Start from ARCHITECTURE.md §7. In Phase 3, expand into a STRIDE table per trust boundary:

1. Browser ↔ API (authentication, CSRF, input validation)
2. API ↔ Workers (queue poisoning, task arguments)
3. Workers ↔ GitHub (token scope, webhook signature verification)
4. Workers ↔ Claude API (data sent, prompt injection, cost abuse)
5. Workers ↔ check-runner sandbox (untrusted code execution)

For each: threat, likelihood, impact, control, test that proves the control works.


---

## Phase 2 controls

### Webhook (`POST /api/webhooks/github`)
- The raw body is verified against `X-Hub-Signature-256` (HMAC-SHA256, constant-time compare)
  *before* it is parsed. With no `DEVPILOT_GITHUB_WEBHOOK_SECRET` the endpoint returns 503, so it
  can never run unauthenticated.
- Only completed, failed `workflow_run` events for **already connected** repositories are acted on.
- Deliveries are idempotent per run id (GitHub retries), so one failure creates one diagnosis.
- Tests: `backend/tests/test_webhooks.py`.

### Check runner (untrusted code execution)
Cloned repositories are untrusted. Each check runs in its own throwaway container that is non-root,
has a read-only root filesystem, `cap_drop=ALL`, `no-new-privileges`, pid/memory/CPU limits, a
timeout (container killed and removed), a read-only mount of the clone, and a tmpfs working copy.
- **Residual risk:** the `check-worker` holds the Docker socket, which is root-equivalent on the
  host. It is therefore a separate, opt-in service that only consumes the `checks` queue, and no
  external input reaches it except repositories you connected yourself. Do not enable it on a
  shared or public host without a socket proxy or rootless Docker/gVisor.
- **Network:** checks need egress to install dependencies (`DEVPILOT_RUNNER_NETWORK=none` makes
  them offline-only). Code in a checked repo can therefore reach the internet.
- Tests: `backend/tests/test_check_runner.py` asserts the sandbox flags on every container.

### Exposure on the VM
Caddy puts HTTP basic auth in front of the dashboard and API. Only the webhook and health probes
are public. This is a stopgap until real authentication (roadmap 1.15).
