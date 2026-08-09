from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from domain.contracts import ACTION_PROTOCOL, SYSTEM_PROMPT
from domain.models import AgentAction, AgentState, SubagentRequest, Task
from ports.audit import AuditPort
from ports.memory import MemoryPort
from ports.model_provider import ModelCallContext, ModelProviderPort
from ports.token_budget import TokenBudgetPort
from ports.tool import ToolRegistryPort


ROLE_PROMPTS = {
    "researcher": "You are a research specialist. Gather precise evidence and return concise findings.",
    "architect": "You are a senior software architect. Review design, contracts, dependencies, risks, and maintainability.",
    "coder": "You are an implementation specialist. Produce concrete implementation guidance or code-oriented findings.",
    "tester": "You are a testing specialist. Identify verification strategy, edge cases, and failure modes.",
    "debugger": "You are a debugging specialist. Focus on reproduction, root cause, and minimal reliable fixes.",
}


@dataclass(slots=True)
class TaskExecutionOutcome:
    finished: bool
    result: str | None = None
    waiting_approval: bool = False
    waiting_user: bool = False
    waiting_reason: str | None = None


class ContextCompressor:
    """Pure application helper that bounds context without knowing storage/vendors."""

    def __init__(self, budget_chars: int = 50_000, preserve_recent: int = 4):
        self._budget_chars = max(4_000, budget_chars)
        self._preserve_recent = max(1, preserve_recent)

    @property
    def budget_chars(self) -> int:
        return self._budget_chars

    @staticmethod
    def _shorten(value: Any, max_chars: int = 1000) -> Any:
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + "...[compressed]"
        if isinstance(value, dict):
            return {k: ContextCompressor._shorten(v, max_chars) for k, v in value.items()}
        if isinstance(value, list):
            return [ContextCompressor._shorten(v, max_chars) for v in value]
        return value

    def compress_rows(self, rows: list[dict], *, budget_chars: int | None = None) -> list[dict]:
        if not rows:
            return []
        effective_budget = max(2_000, int(budget_chars or self._budget_chars))
        recent = rows[-self._preserve_recent :]
        older = rows[: -self._preserve_recent]
        compacted = [self._shorten(dict(row)) for row in older] + [dict(row) for row in recent]
        serialized = json.dumps(compacted, ensure_ascii=False, default=str)
        if len(serialized) <= effective_budget:
            return compacted

        compacted = [self._shorten(dict(row), 350) for row in older] + [dict(row) for row in recent]
        while len(compacted) > self._preserve_recent and len(
            json.dumps(compacted, ensure_ascii=False, default=str)
        ) > effective_budget:
            compacted.pop(0)
        if len(json.dumps(compacted, ensure_ascii=False, default=str)) > effective_budget:
            compacted = [self._shorten(dict(row), 250) for row in compacted]
        return compacted


class ContextBuilder:
    def __init__(self, compressor: ContextCompressor, token_budget: TokenBudgetPort | None = None):
        self._compressor = compressor
        self._token_budget = token_budget

    @staticmethod
    def _short_texts(values: list[Any], max_items: int, max_chars: int) -> list[str]:
        output: list[str] = []
        for value in values[-max_items:]:
            text = str(value)
            output.append(text if len(text) <= max_chars else text[:max_chars] + "...[compressed]")
        return output

    @staticmethod
    def _compact_tool_description(raw: str) -> str:
        try:
            tools = json.loads(raw)
        except Exception:
            return raw
        if not isinstance(tools, list):
            return raw
        compacted = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            row = dict(tool)
            if isinstance(row.get("description"), str) and len(row["description"]) > 240:
                row["description"] = row["description"][:240] + "...[compressed]"
            compacted.append(row)
        return json.dumps(compacted, ensure_ascii=False)

    def build(self, state: AgentState, memories: list[str], tools_description: str) -> str:
        dynamic_budget = (
            self._token_budget.context_budget_chars(state.session_id, self._compressor.budget_chars)
            if self._token_budget
            else self._compressor.budget_chars
        )
        tool_results = self._compressor.compress_rows(
            state.tool_results[-16:], budget_chars=max(2_000, dynamic_budget // 3)
        )
        evidence = state.evidence[-24:]
        context = (
            f"OBJECTIVE:\n{state.objective}\n\n"
            f"CONSTRAINTS:\n{state.constraints}\n\n"
            f"MODE:\n{state.mode.value}\n\n"
            f"RUN STATUS:\n{state.run_status.value}\n\n"
            f"WAITING REASON:\n{state.waiting_reason}\n\n"
            f"PLAN:\n{state.plan.model_dump_json(indent=2)}\n\n"
            f"CURRENT TASK:\n{state.current_task}\n\n"
            f"RECENT EVIDENCE:\n{evidence}\n\n"
            f"RECENT TOOL RESULTS:\n{tool_results}\n\n"
            f"RELEVANT MEMORY:\n{memories}\n\n"
            f"AVAILABLE TOOLS:\n{tools_description}\n"
        )
        if len(context) <= dynamic_budget:
            return context

        compact_evidence = self._short_texts(evidence, 12, 400)
        compact_memories = self._short_texts(memories, 4, 500)
        compact_tools = self._compact_tool_description(tools_description)
        compact_results = self._compressor.compress_rows(
            state.tool_results[-8:], budget_chars=max(2_000, dynamic_budget // 4)
        )
        return (
            f"OBJECTIVE:\n{state.objective}\n\n"
            f"CONSTRAINTS:\n{state.constraints}\n\n"
            f"MODE:\n{state.mode.value}\n\n"
            f"RUN STATUS:\n{state.run_status.value}\n\n"
            f"WAITING REASON:\n{state.waiting_reason}\n\n"
            f"PLAN:\n{state.plan.model_dump_json(indent=2)}\n\n"
            f"CURRENT TASK:\n{state.current_task}\n\n"
            f"RECENT EVIDENCE:\n{compact_evidence}\n\n"
            f"RECENT TOOL RESULTS:\n{compact_results}\n\n"
            f"RELEVANT MEMORY:\n{compact_memories}\n\n"
            f"AVAILABLE TOOLS:\n{compact_tools}\n"
        )


class SubagentCoordinator:
    def __init__(self, provider: ModelProviderPort, max_parallel: int = 6):
        self._provider = provider
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def run(self, role: str, task: str, context: str, *, session_id: str = "") -> str:
        async with self._semaphore:
            system = ROLE_PROMPTS.get(role, f"You are a specialist agent for role: {role}.")
            prompt = f"TASK:\n{task}\n\nCONTEXT:\n{context}\n\nReturn useful findings only."
            return await self._provider.complete(
                prompt,
                system=system,
                context=ModelCallContext(session_id=session_id, purpose=f"subagent:{role}"),
            )

    async def run_many(
        self,
        requests: list[SubagentRequest],
        context: str,
        *,
        session_id: str = "",
    ) -> list[dict[str, str]]:
        async def one(req: SubagentRequest) -> dict[str, str]:
            return {
                "role": req.role,
                "task": req.task,
                "result": await self.run(req.role, req.task, context, session_id=session_id),
            }

        return await asyncio.gather(*(one(req) for req in requests))


class ActionParser:
    def parse(self, raw: str) -> AgentAction:
        return AgentAction.model_validate(json.loads(raw))


class ActionExecutor:
    def __init__(
        self,
        tools: ToolRegistryPort,
        memory: MemoryPort,
        subagents: SubagentCoordinator,
        audit: AuditPort | None = None,
    ):
        self._tools = tools
        self._memory = memory
        self._subagents = subagents
        self._audit = audit

    async def execute(self, action: AgentAction, state: AgentState, context: str) -> TaskExecutionOutcome:
        if self._audit:
            self._audit.record(
                "agent.action",
                session_id=state.session_id,
                data={"action": action.action, "summary": action.thought_summary},
            )
        if action.action == "tool":
            if not action.tool:
                state.evidence.append("Tool action missing tool payload.")
                return TaskExecutionOutcome(False)
            result = await self._tools.call(
                action.tool.name,
                action.tool.arguments,
                session_id=state.session_id,
                user_id=state.user_id,
                task_id=state.current_task or "",
                actor="agent",
            )
            safe_arguments = self._tools.sanitize(action.tool.name, action.tool.arguments)
            row = {
                "tool": action.tool.name,
                "arguments": safe_arguments,
                "ok": result.ok,
                "output": result.output,
                "error": result.error,
                "metadata": result.metadata,
            }
            state.tool_results.append(row)
            changed = result.metadata.get("changed_artifact") if result.metadata else None
            if changed:
                state.changed_artifacts.append(str(changed))
            request = result.metadata.get("approval_required") if result.metadata else None
            if request:
                pending = dict(request)
                pending["tool"] = action.tool.name
                pending["arguments"] = safe_arguments
                if not any(item.get("request_id") == pending.get("request_id") for item in state.pending_approvals):
                    state.pending_approvals.append(pending)
                state.evidence.append(
                    f"Execution paused for approval request {pending.get('request_id', 'unknown')}."
                )
                return TaskExecutionOutcome(False, waiting_approval=True)
            waiting_user = bool(result.metadata.get("waiting_user")) if result.metadata else False
            if waiting_user:
                reason = str(result.metadata.get("reason") or result.error or "User input is required")[:500]
                state.waiting_reason = reason
                state.evidence.append("Browser execution paused because user input is required.")
                return TaskExecutionOutcome(False, waiting_user=True, waiting_reason=reason)
            return TaskExecutionOutcome(False)
        if action.action == "delegate":
            if not action.subagent_task:
                state.evidence.append("Delegate action missing task.")
                return TaskExecutionOutcome(False)
            report = await self._subagents.run(
                action.subagent_role or "researcher",
                action.subagent_task,
                context,
                session_id=state.session_id,
            )
            state.evidence.append(f"Subagent report: {report}")
            return TaskExecutionOutcome(False)
        if action.action == "delegate_parallel":
            if not action.subagents:
                state.evidence.append("Parallel delegate action missing subagents.")
                return TaskExecutionOutcome(False)
            reports = await self._subagents.run_many(
                action.subagents,
                context,
                session_id=state.session_id,
            )
            for report in reports:
                state.evidence.append(f"Parallel subagent [{report['role']}]: {report['result']}")
            return TaskExecutionOutcome(False)
        if action.action == "memory_write":
            if action.memory_key and action.memory_value:
                self._memory.upsert(action.memory_key, action.memory_value)
                state.memories_written.append(action.memory_key)
            return TaskExecutionOutcome(False)
        if action.action == "plan_update":
            if action.plan:
                state.plan = action.plan
                state.evidence.append("Plan updated by agent.")
            return TaskExecutionOutcome(False)
        result = action.result or "Task finished."
        state.final_result = action.result or state.final_result
        state.evidence.append(result)
        return TaskExecutionOutcome(True, result)


class ExecutionEngine:
    def __init__(
        self,
        provider: ModelProviderPort,
        tools: ToolRegistryPort,
        memory: MemoryPort,
        action_executor: ActionExecutor,
        context_builder: ContextBuilder,
        parser: ActionParser | None = None,
    ):
        self._provider = provider
        self._tools = tools
        self._memory = memory
        self._executor = action_executor
        self._context_builder = context_builder
        self._parser = parser or ActionParser()

    async def resume_approved_action(self, pending: dict[str, Any], state: AgentState) -> TaskExecutionOutcome:
        tool_name = str(pending.get("tool", "")).strip()
        if not tool_name:
            state.evidence.append("Approved request had no resumable tool action; continuing with model recovery.")
            return TaskExecutionOutcome(False)

        arguments = dict(pending.get("arguments") or {})
        action_payload = dict(pending.get("action_payload") or {})
        if action_payload.get("url") and not arguments.get("url"):
            arguments["url"] = action_payload["url"]

        result = await self._tools.call(
            tool_name,
            arguments,
            session_id=state.session_id,
            user_id=state.user_id,
            task_id=state.current_task or "",
            actor="agent",
        )
        state.tool_results.append({
            "tool": tool_name,
            "arguments": self._tools.sanitize(tool_name, arguments),
            "ok": result.ok,
            "output": result.output,
            "error": result.error,
            "metadata": result.metadata,
            "resumed_action": True,
        })
        changed = result.metadata.get("changed_artifact") if result.metadata else None
        if changed:
            state.changed_artifacts.append(str(changed))

        next_request = result.metadata.get("approval_required") if result.metadata else None
        if next_request:
            request = dict(next_request)
            request["tool"] = tool_name
            request["arguments"] = self._tools.sanitize(tool_name, arguments)
            if not any(item.get("request_id") == request.get("request_id") for item in state.pending_approvals):
                state.pending_approvals.append(request)
            state.evidence.append("The resumed action still requires approval; execution paused again.")
            return TaskExecutionOutcome(False, waiting_approval=True)

        if result.metadata.get("waiting_user") if result.metadata else False:
            reason = str(result.metadata.get("reason") or result.error or "User input is required")[:500]
            state.waiting_reason = reason
            return TaskExecutionOutcome(False, waiting_user=True, waiting_reason=reason)
        if result.ok:
            state.evidence.append(f"Approved {tool_name} action executed successfully; continuing the task.")
        else:
            state.evidence.append(
                f"Approved {tool_name} action failed during resume: {result.error}. Continuing with recovery context."
            )
        return TaskExecutionOutcome(False)

    async def execute_task(self, task: Task, state: AgentState, max_steps: int) -> TaskExecutionOutcome:
        while state.step_count < max_steps:
            state.step_count += 1
            memories = self._memory.search(state.objective, limit=6)
            state.memories_read = memories
            context = self._context_builder.build(state, memories, self._tools.describe())
            prompt = (
                f"{ACTION_PROTOCOL}\n\nCURRENT TASK:\n{task.model_dump_json(indent=2)}\n\n"
                f"RUNTIME CONTEXT:\n{context}\n"
            )
            raw = await self._provider.complete(
                prompt,
                system=SYSTEM_PROMPT,
                context=ModelCallContext(session_id=state.session_id, purpose="agent_step"),
            )
            try:
                action = self._parser.parse(raw)
            except (json.JSONDecodeError, ValidationError) as exc:
                state.evidence.append(f"Invalid model action: {exc}")
                continue
            outcome = await self._executor.execute(action, state, context)
            if outcome.waiting_approval or outcome.waiting_user or outcome.finished:
                return outcome
        return TaskExecutionOutcome(False)
