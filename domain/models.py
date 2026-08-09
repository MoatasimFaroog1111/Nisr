from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentMode(str, Enum):
    UNDERSTAND = "UNDERSTAND"
    RESEARCH = "RESEARCH"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_USER = "WAITING_USER"
    VERIFICATION = "VERIFICATION"
    DEBUGGING = "DEBUGGING"
    RECOVERY = "RECOVERY"
    DELIVERY = "DELIVERY"


class AgentRunStatus(str, Enum):
    RUNNING = "RUNNING"
    WAITING_TOOL = "WAITING_TOOL"
    WAITING_USER = "WAITING_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class Task(BaseModel):
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    tasks: list[Task] = Field(default_factory=list)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    ok: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    ok: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class SubagentRequest(BaseModel):
    role: str = "researcher"
    task: str


class AgentState(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str = "api"
    browser_session_id: str | None = None
    objective: str
    constraints: list[str] = Field(default_factory=list)
    mode: AgentMode = AgentMode.UNDERSTAND
    run_status: AgentRunStatus = AgentRunStatus.RUNNING
    waiting_reason: str | None = None
    plan: Plan = Field(default_factory=Plan)
    current_task: str | None = None
    completed_tasks: list[str] = Field(default_factory=list)
    blocked_tasks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    changed_artifacts: list[str] = Field(default_factory=list)
    verification_results: list[dict[str, Any]] = Field(default_factory=list)
    memories_read: list[str] = Field(default_factory=list)
    memories_written: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    user_approvals: list[str] = Field(default_factory=list, exclude=True, repr=False)
    pending_approvals: list[dict[str, Any]] = Field(default_factory=list)
    step_count: int = 0
    resume_count: int = 0
    final_result: str | None = None


class AgentAction(BaseModel):
    action: Literal[
        "tool",
        "finish",
        "delegate",
        "delegate_parallel",
        "memory_write",
        "plan_update",
    ]
    thought_summary: str = ""
    tool: ToolCall | None = None
    result: str | None = None
    subagent_role: str | None = None
    subagent_task: str | None = None
    subagents: list[SubagentRequest] = Field(default_factory=list)
    memory_key: str | None = None
    memory_value: str | None = None
    plan: Plan | None = None
