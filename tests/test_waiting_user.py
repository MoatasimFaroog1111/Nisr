from __future__ import annotations

import json

import pytest

from adapters.llm.mock import MockModelAdapter
from adapters.tools.base import BaseTool
from domain.models import AgentMode, AgentRunStatus, TaskStatus, ToolResult
from infrastructure.composition_root import build_runtime
from infrastructure.settings import Settings


class NeedUserTool(BaseTool):
    name = "need_user"
    description = "Test-only tool that requires user input."

    async def run(self, arguments):
        return ToolResult(
            ok=False,
            error="USER_TAKEOVER_REQUIRED",
            metadata={"waiting_user": True, "reason": "otp_or_2fa"},
        )


def make_settings(tmp_path):
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
async def test_agent_enters_waiting_user_and_resumes_same_session_after_return_control(tmp_path):
    provider = MockModelAdapter([
        json.dumps({
            "tasks": [{
                "id": "t1",
                "title": "Verify account",
                "description": "Continue after the user completes 2FA",
                "depends_on": [],
                "verification": [],
            }]
        }),
        json.dumps({
            "action": "tool",
            "thought_summary": "User verification is required",
            "tool": {"name": "need_user", "arguments": {}},
        }),
        json.dumps({
            "action": "finish",
            "thought_summary": "Verification is complete after user returned control",
            "result": "Account verification completed.",
        }),
    ])
    settings = make_settings(tmp_path)
    runtime = build_runtime(settings, provider=provider)
    runtime.tools.register(NeedUserTool())

    state = await runtime.orchestrator.run(
        "Complete account verification",
        session_id="shared-session",
        user_id="user-1",
        browser_session_id="shared-session",
    )

    assert state.session_id == "shared-session"
    assert state.browser_session_id == "shared-session"
    assert state.mode == AgentMode.WAITING_USER
    assert state.run_status == AgentRunStatus.WAITING_USER
    assert state.waiting_reason == "otp_or_2fa"
    assert state.plan.tasks[0].status == TaskStatus.WAITING_USER
    stored = runtime.sessions.load("shared-session")
    assert stored is not None
    assert stored.user_id == "user-1"
    assert stored.mode == AgentMode.WAITING_USER

    resumed = await runtime.orchestrator.resume_user(
        "shared-session",
        {
            "url": "https://example.com/account",
            "title": "Account",
            "tabs": [{"id": "tab-1", "url": "https://example.com/account", "active": True}],
            "control_state": "AGENT_CONTROL",
        },
    )

    assert resumed.session_id == "shared-session"
    assert resumed.resume_count == 1
    assert resumed.run_status == AgentRunStatus.COMPLETED
    assert resumed.mode == AgentMode.DELIVERY
    assert resumed.final_result == "Account verification completed."
    assert resumed.completed_tasks == ["t1"]
    assert any(row.get("tool") == "browser.userObservation" for row in resumed.tool_results)
