from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

import httpx


class OpenAICompatibleAdapter:
    """OpenAI-compatible chat adapter with bounded retry for transient upstream failures."""

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

    async def complete(self, prompt: str, system: str = "") -> str:
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
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for attempt in range(self._max_retries + 1):
                try:
                    response = await client.post(
                        f"{self._api_base}/chat/completions", headers=headers, json=payload
                    )
                    if response.status_code in self._RETRYABLE_STATUS and attempt < self._max_retries:
                        await self._sleep(self._retry_delay(response, attempt))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt >= self._max_retries:
                        raise
                    await self._sleep(self._retry_delay(None, attempt))
        raise RuntimeError("AI provider retry loop exited unexpectedly")
