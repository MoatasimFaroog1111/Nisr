from __future__ import annotations

from dataclasses import dataclass

from domain.models import AgentMode, AgentRunStatus, AgentState, TaskStatus


class StateInvariantViolation(RuntimeError):
    def __init__(self, violations: list[str]):
        super().__init__("; ".join(violations))
        self.violations = violations


@dataclass(frozen=True, slots=True)
class AgentStateInvariantPolicy:
    """Pure domain policy for impossible or contradictory agent states."""

    def violations(self, state: AgentState) -> list[str]:
        problems: list[str] = []
        completed = set(state.completed_tasks)
        blocked = set(state.blocked_tasks)
        overlap = completed & blocked
        if overlap:
            problems.append(f"tasks cannot be both completed and blocked: {sorted(overlap)}")

        waiting_user_tasks = [task.id for task in state.plan.tasks if task.status == TaskStatus.WAITING_USER]
        waiting_approval_tasks = [task.id for task in state.plan.tasks if task.status == TaskStatus.WAITING_APPROVAL]

        if state.run_status == AgentRunStatus.COMPLETED:
            if state.pending_approvals:
                problems.append("completed run cannot have pending approvals")
            if state.waiting_reason:
                problems.append("completed run cannot have a waiting reason")
            if waiting_user_tasks:
                problems.append("completed run cannot contain WAITING_USER tasks")
            if waiting_approval_tasks:
                problems.append("completed run cannot contain WAITING_APPROVAL tasks")
            if blocked:
                problems.append("completed run cannot contain blocked tasks")

        if state.run_status == AgentRunStatus.WAITING_USER or state.mode == AgentMode.WAITING_USER:
            if state.run_status != AgentRunStatus.WAITING_USER or state.mode != AgentMode.WAITING_USER:
                problems.append("WAITING_USER mode and run status must agree")
            if not state.waiting_reason:
                problems.append("WAITING_USER requires a waiting reason")
            if state.current_task and state.current_task not in waiting_user_tasks:
                problems.append("current task must be WAITING_USER while run waits for user")

        if state.mode == AgentMode.WAITING_APPROVAL:
            if state.run_status != AgentRunStatus.WAITING_TOOL:
                problems.append("WAITING_APPROVAL requires WAITING_TOOL run status")
            if not state.pending_approvals:
                problems.append("WAITING_APPROVAL requires at least one pending approval")
            if state.current_task and state.current_task not in waiting_approval_tasks:
                problems.append("current task must be WAITING_APPROVAL while approval is pending")

        if state.run_status == AgentRunStatus.FAILED and state.mode == AgentMode.WAITING_USER:
            problems.append("failed run cannot simultaneously wait for user")

        if state.run_status == AgentRunStatus.CANCELLED and state.mode in {
            AgentMode.WAITING_USER,
            AgentMode.WAITING_APPROVAL,
            AgentMode.EXECUTION,
            AgentMode.VERIFICATION,
        }:
            problems.append("cancelled run cannot remain in an active/waiting execution mode")

        return problems

    def assert_valid(self, state: AgentState) -> None:
        problems = self.violations(state)
        if problems:
            raise StateInvariantViolation(problems)
