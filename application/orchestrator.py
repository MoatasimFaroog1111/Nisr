from __future__ import annotations

from application.execution import ExecutionEngine
from application.planning import PlanningService
from application.verification import VerificationService
from domain.models import AgentMode, AgentState, TaskStatus
from ports.audit import AuditPort


class Orchestrator:
    """Coordinates task lifecycle; delegates planning, execution and verification."""

    def __init__(self, planner: PlanningService, execution: ExecutionEngine, verification: VerificationService, max_steps: int = 30, audit: AuditPort | None = None):
        self._planner = planner
        self._execution = execution
        self._verification = verification
        self._max_steps = max_steps
        self._audit = audit

    async def run(self, objective: str, constraints: list[str] | None = None, approvals: list[str] | None = None) -> AgentState:
        state = AgentState(objective=objective, constraints=constraints or [], user_approvals=approvals or [])
        if self._audit:
            self._audit.record("agent.start", session_id=state.session_id, data={"objective": objective, "constraints": state.constraints})
        state.mode = AgentMode.PLANNING
        state.plan = await self._planner.create_plan(objective, state.constraints)
        if self._audit:
            self._audit.record("plan.created", session_id=state.session_id, data=state.plan.model_dump(mode="json"))
        for task in state.plan.tasks:
            if state.step_count >= self._max_steps:
                break
            if any(dep not in state.completed_tasks for dep in task.depends_on):
                task.status = TaskStatus.BLOCKED
                state.blocked_tasks.append(task.id)
                continue
            task.status = TaskStatus.IN_PROGRESS
            state.current_task = task.id
            state.mode = AgentMode.EXECUTION
            outcome = await self._execution.execute_task(task, state, self._max_steps)
            if not outcome.finished:
                task.status = TaskStatus.BLOCKED
                state.blocked_tasks.append(task.id)
                break
            state.mode = AgentMode.VERIFICATION
            verification = await self._verification.verify(task.verification, state.session_id)
            state.verification_results.append(verification.model_dump())
            if verification.ok:
                task.status = TaskStatus.COMPLETED
                state.completed_tasks.append(task.id)
            else:
                task.status = TaskStatus.BLOCKED
                state.blocked_tasks.append(task.id)
                state.mode = AgentMode.DEBUGGING
                break
        state.mode = AgentMode.DELIVERY
        if state.step_count >= self._max_steps and not state.final_result:
            state.final_result = "Execution stopped at the configured maximum step limit."
        if self._audit:
            self._audit.record("agent.finish", session_id=state.session_id, data={"completed": state.completed_tasks, "blocked": state.blocked_tasks, "steps": state.step_count, "final_result": state.final_result})
        return state
