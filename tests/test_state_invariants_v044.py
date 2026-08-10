from __future__ import annotations

import pytest

from application.guarded_session import GuardedSessionStore
from domain.models import AgentMode, AgentRunStatus, AgentState, Plan, Task, TaskStatus
from domain.state_invariants import AgentStateInvariantPolicy, StateInvariantViolation


class MemoryStore:
    def __init__(self):
        self.state = None
        self.status = None

    def save(self, state, status):
        self.state = state.model_copy(deep=True)
        self.status = status

    def load(self, session_id):
        return self.state.model_copy(deep=True) if self.state and self.state.session_id == session_id else None

    def find_session_by_approval(self, request_id):
        return None


def test_completed_run_cannot_keep_waiting_user_task():
    state = AgentState(
        objective="x",
        mode=AgentMode.DELIVERY,
        run_status=AgentRunStatus.COMPLETED,
        plan=Plan(tasks=[Task(id="t1", title="x", status=TaskStatus.WAITING_USER)]),
    )
    problems = AgentStateInvariantPolicy().violations(state)
    assert any("WAITING_USER" in problem for problem in problems)


def test_completed_run_cannot_have_pending_approval_or_blocked_task():
    state = AgentState(
        objective="x",
        mode=AgentMode.DELIVERY,
        run_status=AgentRunStatus.COMPLETED,
        pending_approvals=[{"request_id": "r1"}],
        blocked_tasks=["t1"],
    )
    problems = AgentStateInvariantPolicy().violations(state)
    assert any("pending approvals" in problem for problem in problems)
    assert any("blocked tasks" in problem for problem in problems)


def test_waiting_user_mode_and_status_must_agree():
    state = AgentState(
        objective="x",
        mode=AgentMode.WAITING_USER,
        run_status=AgentRunStatus.RUNNING,
        waiting_reason="captcha",
        current_task="t1",
        plan=Plan(tasks=[Task(id="t1", title="x", status=TaskStatus.WAITING_USER)]),
    )
    with pytest.raises(StateInvariantViolation):
        AgentStateInvariantPolicy().assert_valid(state)


def test_guarded_session_refuses_invalid_state_before_persistence():
    inner = MemoryStore()
    guarded = GuardedSessionStore(inner)
    invalid = AgentState(
        objective="x",
        mode=AgentMode.DELIVERY,
        run_status=AgentRunStatus.COMPLETED,
        completed_tasks=["t1"],
        blocked_tasks=["t1"],
    )
    with pytest.raises(StateInvariantViolation):
        guarded.save(invalid, "completed")
    assert inner.state is None


def test_guarded_session_allows_consistent_waiting_user_state():
    inner = MemoryStore()
    guarded = GuardedSessionStore(inner)
    state = AgentState(
        session_id="s1",
        objective="x",
        mode=AgentMode.WAITING_USER,
        run_status=AgentRunStatus.WAITING_USER,
        waiting_reason="captcha",
        current_task="t1",
        plan=Plan(tasks=[Task(id="t1", title="x", status=TaskStatus.WAITING_USER)]),
    )
    guarded.save(state, "waiting_user")
    loaded = guarded.load("s1")
    assert loaded is not None
    assert loaded.run_status == AgentRunStatus.WAITING_USER
