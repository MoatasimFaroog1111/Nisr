import json
import pytest
from adapters.llm.mock import MockModelAdapter
from adapters.storage.audit_jsonl import JsonlAuditAdapter
from adapters.storage.memory_sqlite import SqliteMemoryAdapter
from adapters.tools.registry import ToolRegistry
from application.execution import ActionExecutor, ContextBuilder, ContextCompressor, ExecutionEngine, SubagentCoordinator
from domain.models import AgentState, Task

@pytest.mark.asyncio
async def test_execution_engine_finishes_task(tmp_path):
    provider = MockModelAdapter([json.dumps({"action": "finish", "result": "done"})])
    memory = SqliteMemoryAdapter(tmp_path / "memory.sqlite3")
    audit = JsonlAuditAdapter(tmp_path / "audit.jsonl")
    tools = ToolRegistry(audit)
    subagents = SubagentCoordinator(provider)
    executor = ActionExecutor(tools, memory, subagents, audit)
    engine = ExecutionEngine(provider, tools, memory, executor, ContextBuilder(ContextCompressor(10_000)))
    state = AgentState(objective="test")
    outcome = await engine.execute_task(Task(id="t1", title="test"), state, 3)
    assert outcome.finished and state.final_result == "done"
