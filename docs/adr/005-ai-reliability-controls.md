# ADR-005: AI reliability controls (budget, circuit breaker, caching, prompt versions)

**Status:** Accepted (Phase 3)

## Context
Webhook-triggered diagnosis runs unattended. A chatty repository, a Claude outage, or a prompt
change can each cause silent cost, silent quality loss, or a pile-up of failing calls.

## Decision
1. **Per-repository daily token budget** (`DEVPILOT_REPO_DAILY_TOKEN_BUDGET`, default 200k, `0`
   disables). Computed from stored diagnoses for the UTC day. When exhausted, the diagnosis uses
   the offline heuristic, an audit event `diagnosis.budget_exceeded` is written, and a metric is
   incremented.
2. **Circuit breaker around Claude calls.** After N consecutive failures (default 5) calls are
   rejected without touching the network for a cooldown (default 60 s); then one trial request
   decides whether to close it. The diagnoser catches any Claude failure and falls back to the
   heuristic, so a failing API degrades quality, not availability.
3. **Prompt caching.** The system prompt is sent with `cache_control: ephemeral` and cache-read
   tokens are captured. Caching only applies when the cached prefix exceeds the model's minimum
   length, so the current short prompt will usually not hit it. It is cheap to keep and becomes
   effective if the prompt grows (for example with few-shot examples).
4. **Prompt version on every diagnosis** (`PROMPT_VERSION`, stored in `diagnoses.prompt_version`).
   Bump it whenever the prompt, schema or user template changes.
5. **Evals as a regression gate.** `evals/run_evals.py` has three modes: `heuristic` and `fake`
   run on every PR; `real` runs nightly with a hard cost cap. Each is checked against
   `evals/baseline.json`.

## Limits and trade-offs
- The breaker state is per process. With several worker pods each opens independently; that is
  acceptable for a failure signal this coarse. A shared breaker in Redis is a later option.
- The budget is checked before the call, so one large diagnosis can overshoot it once.
- The `/api/diagnose-log` endpoint is not covered by the per-repo budget (SAFETY.md gap G1).
- With only three seed eval cases, the FakeClaude mode validates our guardrails and plumbing, not
  model quality. Real accuracy needs the dataset in roadmap 1.14.
- Heuristic fallback caps confidence at 0.3 and proposes no fix; it is a hint, not a diagnosis.
