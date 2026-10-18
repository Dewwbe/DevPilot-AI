# Safety and Threat Model (living document)

Start from ARCHITECTURE.md §7. In Phase 3, expand into a STRIDE table per trust boundary:

1. Browser ↔ API (authentication, CSRF, input validation)
2. API ↔ Workers (queue poisoning, task arguments)
3. Workers ↔ GitHub (token scope, webhook signature verification)
4. Workers ↔ Claude API (data sent, prompt injection, cost abuse)
5. Workers ↔ check-runner sandbox (untrusted code execution)

For each: threat, likelihood, impact, control, test that proves the control works.
