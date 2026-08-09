from __future__ import annotations

import asyncio
import math
import random
from collections.abc import Awaitable, Callable

import httpx

from ports.model_provider import ModelCallContext
from ports.provider_telemetry import ProviderCallMetrics, ProviderTelemetryPort
from ports.token_budget import TokenBudgetPort


class OpenAICompatibleAdapter:
    """OpenAI-compatible chat adapter with retry, telemetry, and proactive budget throttling."""

    _RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        timeout: float = 90.0,
        *,
        max_retries: int = 2,
        retry_base_seconds: float = 0.8,
        telemetry: ProviderTelemetryPort | None = None,
        token_budget: TokenBudgetPort | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if not model:
            raise ValueError("AGENT_MODEL is required")
        if not api_key:
            raise ValueError("AGENT_API_KEY is required")
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max(0, int(max_retries))
        self._retry_base_seconds = max(0.0, float(retry_base_seconds))
        self._telemetry = telemetry
        self._token_budget = token_budget
        self._transport = transport
        self._sleep = sleep

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return max(0.0, min(float(retry_after), 30.0))
                except ValueError:
                    pass
        exponential = self._retry_base_seconds * (2**attempt)
        jitter = random.uniform(0, self._retry_base_seconds / 4) if self._retry_base_seconds else 0.0
        return min(exponential + jitter, 10.0)

    @staticmethod
    def _int_header(response: httpx.Response, name: str) -> int | None:
        value = response.headers.get(name)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _metrics(
        self,
        response: httpx.Response | None,
        context: ModelCallContext,
        *,
        attempt: int,
        retrying: bool,
        error_type: str | None = None,
    ) -> ProviderCallMetrics:
        usage: dict = {}
        if response is not None and response.status_code < 400:
            try:
                usage = dict(response.json().get("usage") or {})
            except Exception:
                usage = {}
        return ProviderCallMetrics(
            context=context,
            status_code=response.status_code if response is not None else None,
            request_id=response.headers.get("x-request-id") if response is not None else None,
            attempt=attempt,
            retrying=retrying,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            limit_requests=self._int_header(response, "x-ratelimit-limit-requests") if response is not None else None,
            remaining_requests=self._int_header(response, "x-ratelimit-remaining-requests") if response is not None else None,
            reset_requests=response.headers.get("x-ratelimit-reset-requests") if response is not None else None,
            limit_tokens=self._int_header(response, "x-ratelimit-limit-tokens") if response is not None else None,
            remaining_tokens=self._int_header(response, "x-ratelimit-remaining-tokens") if response is not None else None,
            reset_tokens=response.headers.get("x-ratelimit-reset-tokens") if response is not None else None,
            error_type=error_type,
        )

    def _record(self, metrics: ProviderCallMetrics) -> None:
        if self._telemetry:
            self._telemetry.record(metrics)
        if self._token_budget:
            self._token_budget.observe(metrics)

    async def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        context: ModelCallContext | None = None,
    ) -> str:
        call_context = context or ModelCallContext()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        estimated_tokens = (
            self._token_budget.estimate_tokens(len(prompt) + len(system))
            if self._token_budget
            else max(1, math.ceil((len(prompt) + len(system)) / 4))
        )
        if self._token_budget:
            delay = self._token_budget.preflight_delay_seconds(call_context.session_id, estimated_tokens)
            if delay > 0:
                await self._sleep(delay)

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for zero_based_attempt in range(self._max_retries + 1):
                attempt = zero_based_attempt + 1
                try:
                    response = await client.post(
                        f"{self._api_base}/chat/completions", headers=headers, json=payload
                    )
                    should_retry = (
                        response.status_code in self._RETRYABLE_STATUS
                        and zero_based_attempt < self._max_retries
                    )
                    self._record(
                        self._metrics(
                            response,
                            call_context,
                            attempt=attempt,
                            retrying=should_retry,
                        )
                    )
                    if should_retry:
                        await self._sleep(self._retry_delay(response, zero_based_attempt))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    should_retry = zero_based_attempt < self._max_retries
                    self._record(
                        self._metrics(
                            None,
                            call_context,
                            attempt=attempt,
                            retrying=should_retry,
                            error_type=type(exc).__name__,
                        )
                    )
                    if not should_retry:
                        raise
                    await self._sleep(self._retry_delay(None, zero_based_attempt))
        raise RuntimeError("AI provider retry loop exited unexpectedly")
