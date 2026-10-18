"""Thin wrapper around the Claude API.

- Structured output via forced tool use (the model must return JSON matching a schema)
- Timeouts and retries configured on the SDK client
- Token usage + latency captured for cost tracking
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.logging import log


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class LLMUnavailable(RuntimeError):
    pass


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
        started = time.perf_counter()
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            tools=[{"name": tool_name, "description": "Return the result.",
                    "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user}],
        )
        latency = int((time.perf_counter() - started) * 1000)
        block = next(b for b in resp.content if b.type == "tool_use")
        result = LLMResult(
            data=dict(block.input), model=resp.model,
            input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
            latency_ms=latency,
        )
        log.info("llm_call", tool=tool_name, model=result.model, latency_ms=latency,
                 input_tokens=result.input_tokens, output_tokens=result.output_tokens)
        return result
