from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ports.provider_telemetry import ProviderCallMetrics


_DURATION_PART = re.compile(r"([0-9]*\.?[0-9]+)(ms|s|m|h)")


def _duration_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    total = 0.0
    for amount, unit in _DURATION_PART.findall(value.strip().lower()):
        number = float(amount)
        total += number * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    return min(total, 30.0)


@dataclass(slots=True)
class _BudgetState:
    calls: int = 0
    retries: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests: str | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens: str | None = None
    last_request_id: str | None = None


class RunTokenBudgetManager:
    """Vendor-neutral soft budget and proactive throttle for one agent session.

    The budget does not know HTTP or OpenAI headers. Adapters normalize those into
    ProviderCallMetrics before they reach this application service.
    """

    def __init__(
        self,
        *,
        run_token_budget: int = 24_000,
        provider_token_reserve: int = 4_000,
        chars_per_token: float = 4.0,
        min_context_chars: int = 8_000,
        context_safety_ratio: float = 0.65,
    ):
        self._run_token_budget = max(1_000, int(run_token_budget))
        self._provider_token_reserve = max(0, int(provider_token_reserve))
        self._chars_per_token = max(1.0, float(chars_per_token))
        self._min_context_chars = max(2_000, int(min_context_chars))
        self._context_safety_ratio = min(1.0, max(0.1, float(context_safety_ratio)))
        self._states: dict[str, _BudgetState] = {}

    def _state(self, session_id: str) -> _BudgetState:
        return self._states.setdefault(session_id or "__anonymous__", _BudgetState())

    def estimate_tokens(self, char_count: int) -> int:
        return max(1, math.ceil(max(0, int(char_count)) / self._chars_per_token))

    def preflight_delay_seconds(self, session_id: str, estimated_input_tokens: int) -> float:
        state = self._state(session_id)
        delays: list[float] = []
        if state.remaining_requests is not None and state.remaining_requests <= 0:
            delays.append(_duration_seconds(state.reset_requests))
        if state.remaining_tokens is not None:
            needed = max(0, int(estimated_input_tokens)) + self._provider_token_reserve
            if state.remaining_tokens < needed:
                delays.append(_duration_seconds(state.reset_tokens))
        return max(delays, default=0.0)

    def observe(self, metrics: ProviderCallMetrics) -> None:
        state = self._state(metrics.context.session_id)
        state.calls += 1
        if metrics.retrying:
            state.retries += 1
        if metrics.prompt_tokens is not None:
            state.prompt_tokens += max(0, metrics.prompt_tokens)
        if metrics.completion_tokens is not None:
            state.completion_tokens += max(0, metrics.completion_tokens)
        if metrics.total_tokens is not None:
            state.total_tokens += max(0, metrics.total_tokens)
        state.limit_requests = metrics.limit_requests if metrics.limit_requests is not None else state.limit_requests
        state.remaining_requests = metrics.remaining_requests if metrics.remaining_requests is not None else state.remaining_requests
        state.reset_requests = metrics.reset_requests or state.reset_requests
        state.limit_tokens = metrics.limit_tokens if metrics.limit_tokens is not None else state.limit_tokens
        state.remaining_tokens = metrics.remaining_tokens if metrics.remaining_tokens is not None else state.remaining_tokens
        state.reset_tokens = metrics.reset_tokens or state.reset_tokens
        state.last_request_id = metrics.request_id or state.last_request_id

    def context_budget_chars(self, session_id: str, configured_chars: int) -> int:
        state = self._state(session_id)
        configured = max(self._min_context_chars, int(configured_chars))

        run_remaining = max(0, self._run_token_budget - state.total_tokens)
        usable_tokens = run_remaining
        if state.remaining_tokens is not None:
            provider_remaining = max(0, state.remaining_tokens - self._provider_token_reserve)
            usable_tokens = min(usable_tokens, provider_remaining)

        dynamic_chars = int(usable_tokens * self._chars_per_token * self._context_safety_ratio)
        if dynamic_chars <= 0:
            return self._min_context_chars
        return min(configured, max(self._min_context_chars, dynamic_chars))

    def snapshot(self, session_id: str) -> dict:
        state = self._state(session_id)
        return {
            "run_token_budget": self._run_token_budget,
            "run_tokens_used": state.total_tokens,
            "run_tokens_remaining": max(0, self._run_token_budget - state.total_tokens),
            "prompt_tokens": state.prompt_tokens,
            "completion_tokens": state.completion_tokens,
            "calls": state.calls,
            "retries": state.retries,
            "provider_limit_requests": state.limit_requests,
            "provider_remaining_requests": state.remaining_requests,
            "provider_reset_requests": state.reset_requests,
            "provider_limit_tokens": state.limit_tokens,
            "provider_remaining_tokens": state.remaining_tokens,
            "provider_reset_tokens": state.reset_tokens,
            "last_request_id": state.last_request_id,
        }
