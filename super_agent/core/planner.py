from __future__ import annotations

import json
from super_agent.models import Plan, Task
from super_agent.providers.base import ModelProvider


class Planner:
    def __init__(self, provider: ModelProvider):
        self.provider = provider

    async def create_plan(self, objective: str, constraints: list[str]) -> Plan:
        prompt = f"""
Create a compact execution plan for this objective:
{objective}

Constraints:
{constraints}

Return only JSON:
{{
  "tasks": [
    {{
      "id": "t1",
      "title": "...",
      "description": "...",
      "depends_on": [],
      "verification": []
    }}
  ]
}}
Use 1 task if the objective is straightforward. Use multiple small verifiable tasks for complex work.
"""
        raw = await self.provider.complete(prompt, system="You are a task planner. Return valid JSON only.")
        try:
            data = json.loads(raw)
            return Plan.model_validate(data)
        except Exception:
            return Plan(tasks=[
                Task(
                    id="t1",
                    title="Execute objective",
                    description=objective,
                    verification=[],
                )
            ])
