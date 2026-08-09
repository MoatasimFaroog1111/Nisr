import asyncio
import pytest
from application.execution import SubagentCoordinator
from domain.models import SubagentRequest

class SlowProvider:
    async def complete(self, prompt: str, system: str = "") -> str:
        await asyncio.sleep(0.02)
        return "ok"

@pytest.mark.asyncio
async def test_parallel_subagents_return_all_results():
    coordinator = SubagentCoordinator(SlowProvider(), max_parallel=3)
    result = await coordinator.run_many([SubagentRequest(role="researcher", task="a"), SubagentRequest(role="tester", task="b")], "context")
    assert [row["role"] for row in result] == ["researcher", "tester"]
