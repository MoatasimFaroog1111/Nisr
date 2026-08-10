from __future__ import annotations

import pytest

from adapters.tools.browser import BrowserActionTool
from application.orchestrator import Orchestrator
from domain.browser import BrowserState
from domain.models import AgentMode, AgentRunStatus, AgentState, Plan, Task, TaskStatus
from ports.tool import ToolExecutionContext


class FakeBrowserService:
    def __init__(self):
        self.takeover_reasons: list[str] = []

    async def register_session(self, session_id: str, user_id: str):
        return None

    async def navigate(self, session_id: str, user_id: str, task_id: str | None, url: str):
        # Deliberately lightweight action state, matching the production provider's fast path.
        return BrowserState(session_id=session_id, url=url)

    async def get_state(self, session_id: str, user_id: str):
        return BrowserState(
            session_id=session_id,
            url="https://example.test/challenge",
            title="Just a moment...",
            sensitive_signals=["captcha"],
            text_excerpt="must never be exposed to the agent while sensitive",
            interactables=[{"selector": "#secret"}],
        )

    async def request_user_takeover(self, session_id: str, user_id: str, reason: str, *, task_id=None):
        self.takeover_reasons.append(reason)


class InMemorySessions:
    def __init__(self, state: AgentState):
        self.state = state
        self.status = ""

    def save(self, state: AgentState, status: str):
        self.state = state.model_copy(deep=True)
        self.status = status

    def load(self, session_id: str):
        return self.state.model_copy(deep=True) if self.state.session_id == session_id else None


@pytest.mark.asyncio
async def test_navigation_refreshes_state_and_forces_takeover_before_agent_can_finish():
    service = FakeBrowserService()
    tool = BrowserActionTool("navigate", service)
    result = await tool.run_contextual(
        {"url": "https://example.test"},
        ToolExecutionContext(session_id="s1", user_id="u1", task_id="t1"),
    )

    assert result.ok is True
    assert result.metadata["waiting_user"] is True
    assert result.metadata["code"] == "USER_TAKEOVER_REQUIRED"
    assert result.metadata["sensitive_signals"] == ["captcha"]
    assert result.output["text_excerpt"] == ""
    assert result.output["interactables"] == []
    assert service.takeover_reasons == ["captcha"]


@pytest.mark.asyncio
async def test_return_control_does_not_resume_while_sensitive_gate_remains():
    state = AgentState(
        session_id="s2",
        user_id="u2",
        objective="complete verification then continue",
        mode=AgentMode.WAITING_USER,
        run_status=AgentRunStatus.WAITING_USER,
        current_task="t1",
        plan=Plan(tasks=[Task(id="t1", title="browser step", status=TaskStatus.WAITING_USER)]),
    )
    sessions = InMemorySessions(state)
    orchestrator = Orchestrator(None, None, None, sessions=sessions)

    resumed = await orchestrator.resume_user(
        "s2",
        {
            "url": "https://example.test/challenge",
            "title": "Just a moment...",
            "sensitive_signals": ["captcha"],
            "control_state": "AGENT_CONTROL",
        },
    )

    assert resumed is not None
    assert resumed.mode == AgentMode.WAITING_USER
    assert resumed.run_status == AgentRunStatus.WAITING_USER
    assert resumed.plan.tasks[0].status == TaskStatus.WAITING_USER
    assert resumed.resume_count == 0
    assert "captcha" in (resumed.waiting_reason or "")
    assert sessions.status == "waiting_user"


def test_waiting_user_message_never_claims_completion():
    state = AgentState(
        objective="login",
        mode=AgentMode.WAITING_USER,
        run_status=AgentRunStatus.WAITING_USER,
        final_result="Your input is required to continue this step. Take control of the browser when ready.",
    )
    assert state.run_status != AgentRunStatus.COMPLETED
    assert "required" in state.final_result.lower()
