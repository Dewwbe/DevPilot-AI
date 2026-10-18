# ADR-006: Open pull requests for approved fixes through a GitHub App

**Status:** Accepted (Phase 3)

## Context
The core promise is "propose, human approves, nothing changes without review". Turning an approved
fix into a change must not widen what DevPilot can do to a repository.

## Decision
Use a **GitHub App** (not a personal access token) installed on selected repositories with only
**Contents: write** and **Pull requests: write** (plus the mandatory Metadata: read).

Flow: the App's private key signs a short-lived JWT (RS256), which is exchanged for an
installation token. The worker clones the default branch, runs `git apply --check`, creates
`devpilot/fix-<id>`, commits, pushes that branch (never forced), and opens a pull request whose
body carries the root cause, risk, log evidence, the approver and the reviewer's note.

Guardrails:
- Only fixes with status `approved`, a non-empty patch, and no existing PR are accepted.
- DevPilot never pushes to the default branch and never merges; a human reviews and merges, and
  the repository's own CI runs on the PR.
- Patches over 200 KB are refused. A patch that does not apply cleanly stops before any push.
- The token is passed to git through environment variables, never in a URL, and is scrubbed from
  error messages. The clone is deleted afterwards.
- Workflow files are out of reach by construction: the App has no `workflows` permission, so
  GitHub rejects pushes that modify `.github/workflows/`. Such fixes stay as proposals.

## Alternatives considered
- **Fine-grained PAT:** tied to a person, broader and long-lived, hard to audit and rotate.
- **Commit via the Contents API:** avoids git, but cannot apply unified diffs, so patch semantics
  would need a custom implementation.
- **Open the PR automatically on approval:** fewer clicks, but a separate explicit
  `POST /api/fixes/{id}/open-pr` keeps the approval and the outbound write as distinct,
  separately audited steps.

## Consequences
- Setup needs a GitHub App (id, installation id, private key) stored in Secrets Manager under
  `github_app_*`; without them the endpoint returns 503 and the rest of the app is unaffected.
- No UI button yet; the endpoint is available now and the dashboard action is a follow-up.
- Opened PRs come from a bot identity (`DevPilot AI`), so repository branch protection and
  required reviews apply to them like any other contributor.
