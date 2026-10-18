"""Prometheus metrics. The API serves them at /metrics; Celery workers on settings.metrics_port.

Workers must use the threads pool (-P threads) so every task records into this one process.
Dashboards: infra/observability/grafana-dashboard.json.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.core.config import get_settings

DIAGNOSES = Counter("devpilot_diagnoses_total", "Diagnoses produced", ["category", "model"])
DIAGNOSIS_LATENCY = Histogram(
    "devpilot_diagnosis_latency_seconds", "Claude call latency per diagnosis",
    buckets=(0.5, 1, 2, 4, 8, 15, 30, 60),
)
LLM_TOKENS = Counter("devpilot_llm_tokens_total", "LLM tokens", ["model", "direction"])
LLM_COST = Counter("devpilot_llm_cost_usd_total", "Estimated LLM spend in USD", ["model"])
LLM_ERRORS = Counter("devpilot_llm_errors_total", "Failed Claude calls", ["reason"])
LLM_BREAKER_OPEN = Gauge("devpilot_llm_circuit_open", "1 while the Claude circuit breaker is open")
BUDGET_EXCEEDED = Counter("devpilot_budget_exceeded_total", "Diagnoses degraded by token budget")
FIX_DECISIONS = Counter("devpilot_fix_decisions_total", "Human decisions on fixes", ["decision"])
PRS_OPENED = Counter("devpilot_prs_total", "Pull requests for approved fixes", ["result"])
WEBHOOK_EVENTS = Counter("devpilot_webhook_events_total", "GitHub webhook deliveries", ["result"])
HTTP_LATENCY = Histogram(
    "devpilot_http_request_duration_seconds", "API request latency",
    ["method", "route", "status"], buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    s = get_settings()
    return (input_tokens * s.price_input_per_mtok + output_tokens * s.price_output_per_mtok) / 1e6


def record_diagnosis(category: str, model: str, input_tokens: int, output_tokens: int,
                     latency_ms: int) -> None:
    DIAGNOSES.labels(category=category, model=model).inc()
    if model == "heuristic":
        return  # no LLM call happened, so no latency or spend to record
    DIAGNOSIS_LATENCY.observe(latency_ms / 1000)
    record_llm_usage(model, input_tokens, output_tokens)


def record_llm_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    LLM_TOKENS.labels(model=model, direction="input").inc(input_tokens)
    LLM_TOKENS.labels(model=model, direction="output").inc(output_tokens)
    LLM_COST.labels(model=model).inc(estimate_cost_usd(input_tokens, output_tokens))


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def start_worker_server() -> None:
    from prometheus_client import start_http_server

    start_http_server(get_settings().metrics_port)


async def http_metrics_middleware(request, call_next: Callable[[object], Awaitable]):
    started = time.perf_counter()
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")  # template, not raw URL
    if route != "/metrics":
        HTTP_LATENCY.labels(request.method, route, str(response.status_code)).observe(
            time.perf_counter() - started)
    return response
