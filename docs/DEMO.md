# 3-minute demo script

Goal: show the whole loop on a public HTTPS URL: break CI, see a verified diagnosis, approve,
get a pull request, and watch it in the dashboard. The video itself is yours to record; this
is the script and the checklist.

## Before recording (10 minutes)
- [ ] Stack deployed ([DEPLOY-K8S.md](DEPLOY-K8S.md) or [DEPLOY-VM.md](DEPLOY-VM.md)); `https://<host>/readyz` is healthy.
- [ ] Demo target repo connected (dashboard > Repositories) and a repository analysis completed.
- [ ] Webhook configured on the demo repo (events: Workflow runs), delivery shows `200/202`.
- [ ] GitHub App installed on the demo repo (needed for the PR step).
- [ ] Grafana open on the **DevPilot AI** dashboard in a second tab.
- [ ] A commit ready that breaks CI with a missing dependency (and a second one for a failing test).
- [ ] Anthropic key set, so `model` is Claude and not `heuristic`.

## Script

| Time | Say | Show |
|---|---|---|
| 0:00 | "DevPilot diagnoses failed CI runs with Claude, but a human approves anything that changes code." | Dashboard home, one sentence on the architecture diagram |
| 0:20 | "I'll break the build." | Push the failing commit to the demo repo; the Actions run goes red |
| 0:35 | "A signed webhook fires; no one clicked anything." | Webhook delivery in GitHub (HMAC-verified, 202), then the **Diagnoses** page showing the new entry |
| 0:55 | "Category, root cause, and the evidence lines. Each line is checked against the real log, so the model cannot invent evidence. Risk is set by rules, not by the AI." | Open the diagnosis: category `dependency`, confidence, evidence, risk badge, `prompt_version` |
| 1:25 | "Secrets are redacted before anything leaves the system." | Optional: paste a log with `password=...` into Diagnose; show it redacted |
| 1:40 | "I approve it. That is recorded with my name and comment." | Approve the fix (API call or UI), then the **Audit** page entry |
| 2:00 | "Now it becomes a pull request on a new branch. It never pushes to main and never merges." | `POST /api/fixes/<id>/open-pr`, then the PR on GitHub: body with root cause, risk, evidence, approver |
| 2:25 | "I can see what this costs and how reliable it is." | Grafana: latency p95, spend per day, failure categories, approval rate, breaker state |
| 2:45 | "If Claude is down or a repo hits its daily token budget, it degrades to a heuristic instead of failing." | Mention the circuit breaker and budget panels; optionally show `model=heuristic` |
| 2:55 | "Deployed on EKS with Helm, secrets from Secrets Manager, TLS from cert-manager." | `kubectl get pods`, `helm list` |

## If something fails live
- Diagnosis does not appear: check the webhook's Recent Deliveries and `kubectl logs deploy/devpilot-worker`.
- No patch proposed: some failures only get an explanation; use the missing-dependency commit.
- PR step errors: confirm the fix is approved and the GitHub App keys are in Secrets Manager.
- Have a pre-recorded fallback or screenshots of each step.

## Talking points for questions
- **Why not let the AI push fixes?** Trust is earned; every change goes through human review, risk
  rules, and the repo's own CI.
- **How do you stop hallucinations?** Forced tool use with a schema, verbatim evidence check,
  confidence cap, evals gate on every PR. See [ARCHITECTURE.md](ARCHITECTURE.md) section 6 and 9.
- **What would you improve next?** Real authentication (roadmap 1.15), a larger eval set from real
  failures (1.14), rate limiting, and an egress-restricted sandbox. See the gaps in [SAFETY.md](SAFETY.md).
