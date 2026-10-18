# ADR-001: CI failure diagnosis is the core feature

**Status:** Accepted

**Context.** The original concept lists five feature areas. Building all of them shallowly produces a
collection of unrelated demos rather than one convincing product.

**Decision.** The core workflow is: failed CI run → grounded AI diagnosis → human-approved fix.
Repository intelligence feeds context to it; the deployment assistant and observability extend it.

**Consequences.** Phase 1 scope is narrow and demo-able. Features that do not serve the core
workflow are deferred to Phase 3.
