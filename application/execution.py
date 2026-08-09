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
from ports.model_provider import ModelProviderPort
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


class ContextCompressor:
    """Pure application helper that bounds context without knowing storage/vendors."""

    def __init__(self, budget_chars: int = 50_000, preserve_recent: int = 4):
        self._budget_chars = max(4_000, budget_chars)
        self._preserve_recent = max(1, preserve_recent)

    @staticmethod
    def _shorten(value: Any, max_chars: int = 1000) -> Any:
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + "...[compressed]"
        if isinstance(value, dict):
            return {k: ContextCompressor._shorten(v, max_chars) for k, v in value.items()}
        if isinstance(value, list):
            return [ContextCompressor._shorten(v, max_chars) for v in value]
        return value

    def compress_rows(self, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        recent = rows[-self._preserve_recent :]
        older = rows[: -self._preserve_recent]
        compacted = [self._shorten(dict(row)) for row in older] + [dict(row) for row in recent]
        serialized = json.dumps(compacted, ensure_ascii=False, default=str)
        if len(serialized) <= self._budget_chars:
            return compacted
        compressed_older = [self._shorten(dict(row), 350) for row in older]
        return compressed_older + [dict(row) for row in recent]


class ContextBuilder:
    def __init__(self, compressor: ContextCompressor):
        self._compressor = compressor

    def build(self, state: AgentState, memories: list[str], tools_description: str) -> str:
        tool_results = self._compressor.compress_rows(state.tool_results[-16:])
        evidence = state.evidence[-24:]
        return (
            f"OBJECTIVE:\n{state.objective}\n\n"
            f"CONSTRAINTS:\n{state.constraints}\n\n"
            f"MODE:\n{state.mode.value}\n\n"
            f"PLAN:\n{state.plan.model_dump_json(indent=2)}\n\n"
            f"CURRENT TASK:\n{state.current_task}\n\n"
            f"RECENT EVIDENCE:\n{evidence}\n\n"
            f"RECENT TOOL RESULTS:\n{tool_results}\n\n"
            f"RELEVANT MEMORY:\n{memories}\n\n"
            f"AVAILABLE TOOLS:\n{tools_description}\n"
        )


class SubagentCoordinator:
    def __init__(self, provider: ModelProviderPort, max_parallel: int = 6):
        self._provider = provider
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def run(self, role: str, task: str, context: str) -> str:
        async with self._semaphore:
            system = ROLE_PROMPTS.get(role, f"You are a specialist agent for role: {role}.")
            prompt = f"TASK:\n{task}\n\nCONTEXT:\n{context}\n\nReturn useful findings only."
            return await self._provider.complete(prompt, system=system)

    async def run_many(self, requests: list[SubagentRequest], context: str) -> list[dict[str, str]]:
        async def one(req: SubagentRequest) -> dict[str, str]:
            return {"role": req.role, "task": req.task, "result": await self.run(req.role, req.task, context)}
        return await asyncio.gather(*(one(req) for req in requests))


class ActionParser:
    def parse(self, raw: str) -> AgentAction:
        return AgentAction.model_validate(json.loads(raw))


class ActionExecutor:
    def __init__(self, tools: ToolRegistryPort, memory: MemoryPort, subagents: SubagentCoordinator, audit: AuditPort | None = None):
        self._tools = tools
        self._memory = memory
        self._subagents = subagents
        self._audit = audit

    async def execute(self, action: AgentAction, state: AgentState, context: str) -> TaskExecutionOutcome:
        if self._audit:
            self._audit.record("agent.action", session_id=state.session_id, data={"action": action.action, "summary": action.thought_summary})
        if action.action == "tool":
            if not action.tool:
                state.evidence.append("Tool action missing tool payload.")
                return TaskExecutionOutcome(False)
            result = await self._tools.call(action.tool.name, action.tool.arguments, session_id=state.session_id)
            row = {"tool": action.tool.name, "arguments": action.tool.arguments, "ok": result.ok, "output": result.output, "error": result.error, "metadata": result.metadata}
            state.tool_results.append(row)
            changed = result.metadata.get("changed_artifact") if result.metadata else None
            if changed:
                state.changed_artifacts.append(str(changed))
            request = result.metadata.get("approval_required") if result.metadata else None
            if request:
                pending = dict(request)
                pending["tool"] = action.tool.name
                pending["arguments"] = action.tool.arguments
                if not any(item.get("request_id") == pending.get("request_id") for item in state.pending_approvals):
                    state.pending_approvals.append(pending)
                state.evidence.append(
                    f"Execution paused for approval request {pending.get('request_id', 'unknown')}."
                )
                return TaskExecutionOutcome(False, waiting_approval=True)
            return TaskExecutionOutcome(False)
        if action.action == "delegate":
            if not action.subagent_task:
                state.evidence.append("Delegate action missing task.")
                return TaskExecutionOutcome(False)
            report = await self._subagents.run(action.subagent_role or "researcher", action.subagent_task, context)
            state.evidence.append(f"Subagent report: {report}")
            return TaskExecutionOutcome(False)
        if action.action == "delegate_parallel":
            if not action.subagents:
                state.evidence.append("Parallel delegate action missing subagents.")
                return TaskExecutionOutcome(False)
            reports = await self._subagents.run_many(action.subagents, context)
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
    def __init__(self, provider: ModelProviderPort, tools: ToolRegistryPort, memory: MemoryPort, action_executor: ActionExecutor, context_builder: ContextBuilder, parser: ActionParser | None = None):
        self._provider = provider
        self._tools = tools
        self._memory = memory
        self._executor = action_executor
        self._context_builder = context_builder
        self._parser = parser or ActionParser()

    async def execute_task(self, task: Task, state: AgentState, max_steps: int) -> TaskExecutionOutcome:
        while state.step_count < max_steps:
            state.step_count += 1
            memories = self._memory.search(state.objective, limit=6)
            state.memories_read = memories
            context = self._context_builder.build(state, memories, self._tools.describe())
            prompt = f"{ACTION_PROTOCOL}\n\nCURRENT TASK:\n{task.model_dump_json(indent=2)}\n\nRUNTIME CONTEXT:\n{context}\n"
            raw = await self._provider.complete(prompt, system=SYSTEM_PROMPT)
            try:
                action = self._parser.parse(raw)
            except (json.JSONDecodeError, ValidationError) as exc:
                state.evidence.append(f"Invalid model action: {exc}")
                continue
            outcome = await self._executor.execute(action, state, context)
            if outcome.waiting_approval or outcome.finished:
                return outcome
        return TaskExecutionOutcome(False)
