from __future__ import annotations

from application.execution import ExecutionEngine
from application.planning import PlanningService
from application.verification import VerificationService
from domain.models import AgentMode, AgentState, TaskStatus
from ports.audit import AuditPort
from ports.session import SessionStorePort


class Orchestrator:
    """Coordinates task lifecycle; delegates planning, execution and verification."""

    def __init__(
        self,
        planner: PlanningService,
        execution: ExecutionEngine,
        verification: VerificationService,
        max_steps: int = 30,
        audit: AuditPort | None = None,
        sessions: SessionStorePort | None = None,
    ):
        self._planner = planner
        self._execution = execution
        self._verification = verification
        self._max_steps = max_steps
        self._audit = audit
        self._sessions = sessions

    def _save(self, state: AgentState, status: str) -> None:
        if self._sessions:
            self._sessions.save(state, status)

    def _mark_waiting(self, state: AgentState) -> AgentState:
        if state.current_task:
            for task in state.plan.tasks:
                if task.id == state.current_task:
                    task.status = TaskStatus.WAITING_APPROVAL
                    break
        state.mode = AgentMode.WAITING_APPROVAL
        state.final_result = "Waiting for your approval before continuing this task."
        self._save(state, "waiting_approval")
        if self._audit:
            self._audit.record(
                "agent.waiting_approval",
                session_id=state.session_id,
                data={"task": state.current_task, "pending_approvals": state.pending_approvals},
            )
        return state

    async def _continue(self, state: AgentState, step_limit: int) -> AgentState:
        for task in state.plan.tasks:
            if task.id in state.completed_tasks or task.status == TaskStatus.COMPLETED:
                continue
            if state.step_count >= step_limit:
                break
            if any(dep not in state.completed_tasks for dep in task.depends_on):
                task.status = TaskStatus.BLOCKED
                if task.id not in state.blocked_tasks:
                    state.blocked_tasks.append(task.id)
                continue

            task.status = TaskStatus.IN_PROGRESS
            state.current_task = task.id
            state.mode = AgentMode.EXECUTION
            self._save(state, "running")
            outcome = await self._execution.execute_task(task, state, step_limit)

            if outcome.waiting_approval:
                return self._mark_waiting(state)

            if not outcome.finished:
                task.status = TaskStatus.BLOCKED
                if task.id not in state.blocked_tasks:
                    state.blocked_tasks.append(task.id)
                break

            state.mode = AgentMode.VERIFICATION
            verification = await self._verification.verify(task.verification, state.session_id)
            state.verification_results.append(verification.model_dump())
            if verification.ok:
                task.status = TaskStatus.COMPLETED
                if task.id not in state.completed_tasks:
                    state.completed_tasks.append(task.id)
            else:
                task.status = TaskStatus.BLOCKED
                if task.id not in state.blocked_tasks:
                    state.blocked_tasks.append(task.id)
                state.mode = AgentMode.DEBUGGING
                break
            self._save(state, "running")

        state.mode = AgentMode.DELIVERY
        if state.step_count >= step_limit and not state.final_result:
            state.final_result = "Execution stopped at the configured maximum step limit."
        self._save(state, "completed" if not state.blocked_tasks else "blocked")
        if self._audit:
            self._audit.record(
                "agent.finish",
                session_id=state.session_id,
                data={
                    "completed": state.completed_tasks,
                    "blocked": state.blocked_tasks,
                    "steps": state.step_count,
                    "resume_count": state.resume_count,
                    "final_result": state.final_result,
                },
            )
        return state

    async def run(
        self,
        objective: str,
        constraints: list[str] | None = None,
        approvals: list[str] | None = None,
    ) -> AgentState:
        state = AgentState(
            objective=objective,
            constraints=constraints or [],
            user_approvals=approvals or [],
        )
        if self._audit:
            self._audit.record(
                "agent.start",
                session_id=state.session_id,
                data={"objective": objective, "constraints": state.constraints},
            )
        state.mode = AgentMode.PLANNING
        state.plan = await self._planner.create_plan(objective, state.constraints)
        self._save(state, "running")
        if self._audit:
            self._audit.record(
                "plan.created",
                session_id=state.session_id,
                data=state.plan.model_dump(mode="json"),
            )
        return await self._continue(state, self._max_steps)

    async def resume(
        self,
        session_id: str,
        approvals: list[str],
        approved_request_id: str,
    ) -> AgentState:
        if not self._sessions:
            raise RuntimeError("Session persistence is not configured")
        state = self._sessions.load(session_id)
        if not state:
            raise KeyError("Unknown agent session")

        pending = next(
            (
                request
                for request in state.pending_approvals
                if request.get("request_id") == approved_request_id
            ),
            None,
        )
        state.user_approvals.extend(token for token in approvals if token not in state.user_approvals)
        state.pending_approvals = [
            request
            for request in state.pending_approvals
            if request.get("request_id") != approved_request_id
        ]
        state.resume_count += 1
        state.final_result = None
        state.evidence.append(
            f"Approval {approved_request_id} granted; resuming the paused task."
        )

        if state.current_task:
            for task in state.plan.tasks:
                if task.id == state.current_task and task.status == TaskStatus.WAITING_APPROVAL:
                    task.status = TaskStatus.PENDING
                    break
            state.blocked_tasks = [task_id for task_id in state.blocked_tasks if task_id != state.current_task]

        state.mode = AgentMode.RECOVERY
        self._save(state, "resuming")
        if self._audit:
            self._audit.record(
                "agent.resume",
                session_id=state.session_id,
                data={"approval_request_id": approved_request_id, "resume_count": state.resume_count},
            )

        if pending:
            replay = await self._execution.resume_approved_action(pending, state)
            if replay.waiting_approval:
                return self._mark_waiting(state)
            self._save(state, "resuming")

        return await self._continue(state, state.step_count + self._max_steps)

    def deny(self, session_id: str, denied_request_id: str) -> AgentState:
        if not self._sessions:
            raise RuntimeError("Session persistence is not configured")
        state = self._sessions.load(session_id)
        if not state:
            raise KeyError("Unknown agent session")

        state.pending_approvals = [
            request
            for request in state.pending_approvals
            if request.get("request_id") != denied_request_id
        ]
        if state.current_task:
            for task in state.plan.tasks:
                if task.id == state.current_task:
                    task.status = TaskStatus.BLOCKED
                    break
            if state.current_task not in state.blocked_tasks:
                state.blocked_tasks.append(state.current_task)
        state.mode = AgentMode.DELIVERY
        state.final_result = "Approval denied. The protected action was not executed."
        state.evidence.append(
            f"Approval {denied_request_id} was denied; the protected action was not executed."
        )
        self._save(state, "denied")
        if self._audit:
            self._audit.record(
                "agent.approval_denied",
                session_id=state.session_id,
                data={"approval_request_id": denied_request_id, "task": state.current_task},
            )
        return state
