# ADR-004: Observability with Prometheus metrics, Grafana and CloudWatch logs

**Status:** Accepted (Phase 3)

## Context
For an AI feature the useful questions are not only "is it up" but "how slow is Claude, what does
it cost per day, which failure categories dominate, how often do humans approve the fix, and are
we silently falling back to the heuristic". Logs alone answer none of these cheaply.

## Decision
- **Metrics:** `prometheus_client` in the API (`/metrics`) and in each Celery worker (port 9100).
  Series: `devpilot_diagnoses_total{category,model}`, `devpilot_diagnosis_latency_seconds`,
  `devpilot_llm_tokens_total`, `devpilot_llm_cost_usd_total`, `devpilot_llm_errors_total`,
  `devpilot_llm_circuit_open`, `devpilot_fix_decisions_total`, `devpilot_budget_exceeded_total`,
  `devpilot_prs_total`, `devpilot_webhook_events_total` and API request latency by route template.
- **Dashboards and alerts** ship in the Helm chart (a labelled ConfigMap for the Grafana sidecar
  and a `PrometheusRule`), so they deploy and version with the app.
- **Logs:** structlog JSON to stdout, collected by the EKS `amazon-cloudwatch-observability`
  addon into CloudWatch Logs.
- **Cost is an estimate:** tokens x configurable prices (`DEVPILOT_PRICE_*_PER_MTOK`). It is for
  trend and alerting, not billing; the Anthropic console is the source of truth.

## Consequences
- Celery must use the **threads pool** (`-P threads`). Prefork children would record metrics in
  processes the exporter cannot see. Concurrency is I/O bound (HTTP and DB), so threads are fine.
  CPU-heavy work would need a different design (multiprocess mode or a pushgateway).
- `/metrics` is deliberately not exposed through the ingress; Prometheus scrapes it in-cluster.
- Prometheus Operator CRDs are required for `ServiceMonitor` and `PrometheusRule`;
  `monitoring.serviceMonitor` is off by default so the chart installs without them.
- Per-diagnosis detail lives in Postgres (tokens, latency, `prompt_version`); metrics are
  aggregate and reset on pod restart, so use `increase()` and rate queries.
