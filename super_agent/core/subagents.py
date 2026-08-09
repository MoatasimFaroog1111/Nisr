from __future__ import annotations

import asyncio
from super_agent.providers.base import ModelProvider
from super_agent.models import SubagentRequest


ROLE_PROMPTS = {
    "researcher": "You are a research specialist. Gather precise evidence and return concise findings.",
    "architect": "You are a senior software architect. Review design, contracts, dependencies, risks, and maintainability.",
    "coder": "You are an implementation specialist. Produce concrete implementation guidance or code-oriented findings.",
    "tester": "You are a testing specialist. Identify verification strategy, edge cases, and failure modes.",
    "debugger": "You are a debugging specialist. Focus on reproduction, root cause, and minimal reliable fixes.",
}


class SubagentManager:
    def __init__(self, provider: ModelProvider, max_parallel: int = 6):
        self.provider = provider
        self._semaphore = asyncio.Semaphore(max_parallel)

    async def run(self, role: str, task: str, context: str) -> str:
        async with self._semaphore:
            system = ROLE_PROMPTS.get(role, f"You are a specialist agent for role: {role}.")
            prompt = f"TASK:\n{task}\n\nCONTEXT:\n{context}\n\nReturn useful findings only."
            return await self.provider.complete(prompt, system=system)

    async def run_many(self, requests: list[SubagentRequest], context: str) -> list[dict[str, str]]:
        async def one(req: SubagentRequest):
            result = await self.run(req.role, req.task, context)
            return {"role": req.role, "task": req.task, "result": result}
        return await asyncio.gather(*(one(req) for req in requests))
