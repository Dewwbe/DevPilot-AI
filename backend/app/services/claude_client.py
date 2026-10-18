"""Thin wrapper around the Claude API.

- Structured output via forced tool use (the model must return JSON matching a schema)
- Timeouts and retries configured on the SDK client
- Token usage + latency captured for cost tracking
- Circuit breaker: after repeated failures calls are short-circuited so workers don't pile up
  against a failing API; callers fall back to the offline heuristic
- Prompt caching: the system prompt is marked cacheable (it only takes effect once the cached
  prefix exceeds the model's minimum cacheable length, so short prompts simply don't cache)
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core import metrics
from app.core.config import get_settings
from app.core.logging import log


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMUnavailable(RuntimeError):
    pass


class CircuitBreaker:
    """Closed -> open after `threshold` consecutive failures -> half-open after `cooldown_s`.

    While open every call is rejected. In half-open state one trial call is let through: success
    closes the breaker, failure re-opens it for another cooldown.
    """

    def __init__(self, threshold: int, cooldown_s: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold, self.cooldown_s, self._clock = threshold, cooldown_s, clock
        self._failures = 0
        self._opened_at: float | None = None
        self._trial_in_flight = False
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._opened_at is not None

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at >= self.cooldown_s and not self._trial_in_flight:
                self._trial_in_flight = True  # half-open: exactly one trial request
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures, self._opened_at, self._trial_in_flight = 0, None, False
        metrics.LLM_BREAKER_OPEN.set(0)

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._trial_in_flight = False
            if self._failures >= self.threshold or self._opened_at is not None:
                self._opened_at = self._clock()
        if self.is_open:
            metrics.LLM_BREAKER_OPEN.set(1)


_breaker: CircuitBreaker | None = None


def get_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        s = get_settings()
        _breaker = CircuitBreaker(s.llm_breaker_threshold, s.llm_breaker_cooldown_s)
    return _breaker


class ClaudeClient:
    def __init__(self) -> None:
        s = get_settings()
        if not s.anthropic_api_key:
            raise LLMUnavailable("DEVPILOT_ANTHROPIC_API_KEY is not set")
        import anthropic  # imported lazily so tests run without the key

        self._client = anthropic.Anthropic(
            api_key=s.anthropic_api_key,
            timeout=s.claude_timeout_s,
            max_retries=s.claude_max_retries,
        )
        self._model = s.claude_model
        self._max_tokens = s.claude_max_tokens

    def structured(self, *, system: str, user: str, tool_name: str,
                   schema: dict[str, Any]) -> LLMResult:
        breaker = get_breaker()
        if not breaker.allow():
            metrics.LLM_ERRORS.labels(reason="circuit_open").inc()
            raise LLMUnavailable("Claude circuit breaker is open; using offline fallback")

        started = time.perf_counter()
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=[{"name": tool_name, "description": "Return the result.",
                        "input_schema": schema}],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            breaker.record_failure()
            metrics.LLM_ERRORS.labels(reason=type(exc).__name__).inc()
            raise
        breaker.record_success()

        latency = int((time.perf_counter() - started) * 1000)
        block = next(b for b in resp.content if b.type == "tool_use")
        usage = resp.usage
        result = LLMResult(
            data=dict(block.input), model=resp.model,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            latency_ms=latency,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )
        log.info("llm_call", tool=tool_name, model=result.model, latency_ms=latency,
                 input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                 cache_read_tokens=result.cache_read_tokens)
        return result
