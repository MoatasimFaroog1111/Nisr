from __future__ import annotations

import json

import httpx
import pytest

from adapters.llm.mock import MockModelAdapter
from adapters.llm.openai_compatible import OpenAICompatibleAdapter
from domain.provider import ProviderAuthenticationError
from infrastructure.composition_root import build_runtime
from infrastructure.settings import Settings


@pytest.mark.asyncio
async def test_openai_adapter_retries_rate_limit_then_succeeds():
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"message": "busy"}})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "RECOVERED"}}]},
        )

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    adapter = OpenAICompatibleAdapter(
        "https://provider.example/v1",
        "test-key",
        "test-model",
        max_retries=2,
        retry_base_seconds=0,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
    )
    result = await adapter.complete("hello")

    assert result == "RECOVERED"
    assert attempts == 3
    assert len(sleeps) == 2


@pytest.mark.asyncio
async def test_openai_adapter_does_not_retry_auth_errors():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    adapter = OpenAICompatibleAdapter(
        "https://provider.example/v1",
        "test-key",
        "test-model",
        max_retries=5,
        retry_base_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderAuthenticationError) as exc_info:
        await adapter.complete("hello")
    assert exc_info.value.retryable is False
    assert exc_info.value.status_code == 401
    assert attempts == 1


def _settings(tmp_path) -> Settings:
    return Settings(
        provider="mock",
        model="mock",
        api_base="http://example.invalid",
        api_key="x",
        workspace=tmp_path / "workspace",
        memory_db=tmp_path / "memory.sqlite3",
        approval_db=tmp_path / "approvals.sqlite3",
        session_db=tmp_path / "sessions.sqlite3",
        approval_secret="test-secret",
        browser_session_secret="browser-secret",
        audit_log=tmp_path / "audit.jsonl",
        artifacts_dir=tmp_path / "artifacts",
        database_url="",
        max_steps=5,
    )


@pytest.mark.asyncio
async def test_return_control_does_not_fake_resume_non_waiting_run(tmp_path):
    provider = MockModelAdapter([
        json.dumps({
            "tasks": [{
                "id": "t1",
                "title": "Finish",
                "description": "Finish normally",
                "depends_on": [],
                "verification": [],
            }]
        }),
        json.dumps({"action": "finish", "result": "done"}),
    ])
    runtime = build_runtime(_settings(tmp_path), provider=provider)
    state = await runtime.orchestrator.run(
        "finish",
        session_id="same-session",
        user_id="user-1",
        browser_session_id="same-session",
    )
    assert state.run_status.value == "COMPLETED"

    resumed = await runtime.orchestrator.resume_user(
        "same-session",
        {"url": "https://example.com", "tabs": []},
    )
    assert resumed is None
