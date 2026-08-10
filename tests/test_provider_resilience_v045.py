from __future__ import annotations

import httpx
import pytest

from adapters.llm.openai_compatible import OpenAICompatibleAdapter
from application.provider_resilience import ProviderCandidate, ResilientModelProvider
from domain.provider import ModelCallContext, ProviderAuthenticationError, ProviderUnavailableError


class RecordingProvider:
    def __init__(self, *, result: str | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.contexts: list[ModelCallContext | None] = []

    async def complete(self, prompt: str, system: str = "", *, context: ModelCallContext | None = None) -> str:
        self.contexts.append(context)
        if self.error:
            raise self.error
        return self.result or "ok"


class AuditCollector:
    def __init__(self):
        self.rows: list[tuple[str, str, dict]] = []

    def record(self, event: str, *, session_id: str = "", data: dict | None = None):
        self.rows.append((event, session_id, data or {}))

    def tail(self, limit: int = 100):
        return []


@pytest.mark.asyncio
async def test_retryable_primary_failure_uses_fallback_with_same_session_context():
    primary = RecordingProvider(error=ProviderUnavailableError("temporary", retryable=True, status_code=429))
    fallback = RecordingProvider(result="fallback-ok")
    audit = AuditCollector()
    provider = ResilientModelProvider(
        [ProviderCandidate("primary", primary), ProviderCandidate("fallback", fallback)],
        audit=audit,
    )
    context = ModelCallContext(session_id="session-123", purpose="agent_step")

    result = await provider.complete("secret prompt", system="system", context=context)

    assert result == "fallback-ok"
    assert primary.contexts == [context]
    assert fallback.contexts == [context]
    assert any(row[0] == "provider.candidate_failed" for row in audit.rows)
    assert any(row[0] == "provider.fallback_succeeded" for row in audit.rows)
    assert "secret prompt" not in repr(audit.rows)


@pytest.mark.asyncio
async def test_non_retryable_auth_failure_does_not_fallback():
    primary = RecordingProvider(error=ProviderAuthenticationError("bad auth", retryable=False, status_code=401))
    fallback = RecordingProvider(result="must-not-run")
    provider = ResilientModelProvider(
        [ProviderCandidate("primary", primary), ProviderCandidate("fallback", fallback)]
    )

    with pytest.raises(ProviderAuthenticationError):
        await provider.complete("x", context=ModelCallContext(session_id="s"))
    assert fallback.contexts == []


@pytest.mark.asyncio
async def test_openai_adapter_normalizes_final_429_for_failover():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"x-request-id": "req_429", "retry-after": "0"}, json={"error": {"message": "rate"}})

    adapter = OpenAICompatibleAdapter(
        "https://provider.example/v1",
        "key",
        "model",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await adapter.complete("x", context=ModelCallContext(session_id="s"))
    assert exc_info.value.status_code == 429
    assert exc_info.value.request_id == "req_429"
    assert exc_info.value.retryable is True
