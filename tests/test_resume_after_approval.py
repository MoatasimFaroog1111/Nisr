import json

import pytest

from adapters.llm.mock import MockModelAdapter
from domain.models import AgentMode, TaskStatus
from infrastructure.composition_root import build_runtime
from infrastructure.settings import Settings


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
        audit_log=tmp_path / "audit.jsonl",
        artifacts_dir=tmp_path / "artifacts",
        database_url="",
        max_steps=5,
    )


def approval_provider():
    return MockModelAdapter([
        json.dumps({
            "tasks": [{
                "id": "t1",
                "title": "Write protected file",
                "description": "Write only after explicit approval",
                "depends_on": [],
                "verification": [],
            }]
        }),
        json.dumps({
            "action": "tool",
            "thought_summary": "Write requested file",
            "tool": {
                "name": "write_file",
                "arguments": {"path": "approved.txt", "content": "approved"},
            },
        }),
        json.dumps({"action": "finish", "result": "Approved write completed"}),
    ])


@pytest.mark.asyncio
async def test_approval_resumes_same_durable_session(tmp_path):
    provider = approval_provider()
    settings = make_settings(tmp_path)

    first_runtime = build_runtime(settings, provider=provider)
    paused = await first_runtime.orchestrator.run("Write approved.txt only after approval")

    assert paused.mode == AgentMode.WAITING_APPROVAL
    assert paused.plan.tasks[0].status == TaskStatus.WAITING_APPROVAL
    assert paused.pending_approvals
    assert not (settings.workspace / "approved.txt").exists()

    request_id = paused.pending_approvals[0]["request_id"]
    assert first_runtime.sessions.find_session_by_approval(request_id) == paused.session_id

    token = first_runtime.approvals.approve(request_id)
    second_runtime = build_runtime(settings, provider=provider, approvals=[token])
    resumed = await second_runtime.orchestrator.resume(
        paused.session_id,
        approvals=[token],
        approved_request_id=request_id,
    )

    assert resumed.session_id == paused.session_id
    assert resumed.resume_count == 1
    assert resumed.mode == AgentMode.DELIVERY
    assert resumed.pending_approvals == []
    assert resumed.completed_tasks == ["t1"]
    assert resumed.final_result == "Approved write completed"
    assert (settings.workspace / "approved.txt").read_text(encoding="utf-8") == "approved"


@pytest.mark.asyncio
async def test_denial_closes_same_session_without_executing_action(tmp_path):
    provider = approval_provider()
    settings = make_settings(tmp_path)
    runtime = build_runtime(settings, provider=provider)
    paused = await runtime.orchestrator.run("Write approved.txt only after approval")
    request_id = paused.pending_approvals[0]["request_id"]

    runtime.approvals.deny(request_id)
    denied = runtime.orchestrator.deny(paused.session_id, request_id)

    assert denied.session_id == paused.session_id
    assert denied.mode == AgentMode.DELIVERY
    assert denied.pending_approvals == []
    assert denied.blocked_tasks == ["t1"]
    assert denied.plan.tasks[0].status == TaskStatus.BLOCKED
    assert denied.final_result == "Approval denied. The protected action was not executed."
    assert not (settings.workspace / "approved.txt").exists()


def test_session_store_round_trip_and_approval_link(tmp_path):
    from adapters.storage.session_sqlite import SqliteSessionStore
    from domain.models import AgentState

    store = SqliteSessionStore(tmp_path / "sessions.sqlite3")
    state = AgentState(
        objective="test",
        pending_approvals=[{"request_id": "req-1", "risk": "medium"}],
    )
    store.save(state, "waiting_approval")

    loaded = store.load(state.session_id)
    assert loaded is not None
    assert loaded.session_id == state.session_id
    assert store.find_session_by_approval("req-1") == state.session_id
