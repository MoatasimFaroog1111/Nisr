from __future__ import annotations

import httpx
import pytest

from adapters.llm.openai_compatible import OpenAICompatibleAdapter
from adapters.telemetry.provider_audit import AuditProviderTelemetry
from application.token_budget import RunTokenBudgetManager
from ports.model_provider import ModelCallContext
from ports.provider_telemetry import ProviderCallMetrics


class TelemetryCollector:
    def __init__(self):
        self.rows: list[ProviderCallMetrics] = []

    def record(self, metrics: ProviderCallMetrics) -> None:
        self.rows.append(metrics)


class AuditCollector:
    def __init__(self):
        self.rows: list[dict] = []

    def record(self, event: str, *, session_id: str = "", data: dict | None = None) -> None:
        self.rows.append({"event": event, "session_id": session_id, "data": data or {}})

    def tail(self, limit: int = 100) -> list[dict]:
        return self.rows[-limit:]


@pytest.mark.asyncio
async def test_provider_records_normalized_rate_limits_and_usage_without_payload():
    telemetry = TelemetryCollector()
    budget = RunTokenBudgetManager(run_token_budget=24_000, provider_token_reserve=4_000)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "super-secret-prompt" in request.content.decode()
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            headers={
                "x-request-id": "req_test_123",
                "x-ratelimit-limit-requests": "500",
                "x-ratelimit-remaining-requests": "499",
                "x-ratelimit-reset-requests": "120ms",
                "x-ratelimit-limit-tokens": "30000",
                "x-ratelimit-remaining-tokens": "28000",
                "x-ratelimit-reset-tokens": "8ms",
            },
            json={
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 8, "total_tokens": 128},
            },
        )

    adapter = OpenAICompatibleAdapter(
        "https://provider.example/v1",
        "test-key",
        "test-model",
        telemetry=telemetry,
        token_budget=budget,
        transport=httpx.MockTransport(handler),
    )
    result = await adapter.complete(
        "super-secret-prompt",
        context=ModelCallContext(session_id="run-1", purpose="agent_step"),
    )

    assert result == "OK"
    assert len(telemetry.rows) == 1
    row = telemetry.rows[0]
    assert row.request_id == "req_test_123"
    assert row.limit_requests == 500
    assert row.remaining_requests == 499
    assert row.limit_tokens == 30000
    assert row.remaining_tokens == 28000
    assert row.total_tokens == 128
    assert "super-secret-prompt" not in repr(row)
    assert "test-key" not in repr(row)

    snapshot = budget.snapshot("run-1")
    assert snapshot["run_tokens_used"] == 128
    assert snapshot["provider_remaining_tokens"] == 28000
    assert snapshot["last_request_id"] == "req_test_123"


def test_budget_compresses_context_and_recommends_wait_near_provider_limit():
    budget = RunTokenBudgetManager(
        run_token_budget=24_000,
        provider_token_reserve=4_000,
        chars_per_token=4.0,
        min_context_chars=8_000,
        context_safety_ratio=0.65,
    )
    budget.observe(
        ProviderCallMetrics(
            context=ModelCallContext(session_id="run-2", purpose="agent_step"),
            status_code=200,
            request_id="req_limit",
            total_tokens=18_000,
            prompt_tokens=17_000,
            completion_tokens=1_000,
            limit_tokens=30_000,
            remaining_tokens=6_000,
            reset_tokens="1.5s",
            limit_requests=500,
            remaining_requests=499,
            reset_requests="100ms",
        )
    )

    assert budget.context_budget_chars("run-2", 50_000) == 8_000
    assert budget.preflight_delay_seconds("run-2", 3_000) == 1.5
    snapshot = budget.snapshot("run-2")
    assert snapshot["run_tokens_remaining"] == 6_000
    assert snapshot["provider_remaining_tokens"] == 6_000


def test_audit_provider_telemetry_never_receives_prompt_or_credentials():
    audit = AuditCollector()
    adapter = AuditProviderTelemetry(audit)
    adapter.record(
        ProviderCallMetrics(
            context=ModelCallContext(session_id="run-3", purpose="planning"),
            status_code=429,
            request_id="req_429",
            attempt=2,
            retrying=True,
            remaining_tokens=0,
            reset_tokens="900ms",
            error_type="rate_limit",
        )
    )

    assert len(audit.rows) == 1
    serialized = repr(audit.rows[0])
    assert "provider.telemetry" in serialized
    assert "req_429" in serialized
    assert "super-secret-prompt" not in serialized
    assert "Bearer test-key" not in serialized
    assert "authorization" not in serialized.lower()
    assert "api_key" not in serialized.lower()
