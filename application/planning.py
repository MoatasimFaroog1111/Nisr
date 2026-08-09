from __future__ import annotations

import json

from application.model_calls import complete_model
from domain.models import Plan, Task
from domain.provider import ModelCallContext
from ports.model_provider import ModelProviderPort


class PlanningService:
    def __init__(self, provider: ModelProviderPort):
        self._provider = provider

    async def create_plan(self, objective: str, constraints: list[str], *, session_id: str = "") -> Plan:
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
        raw = await complete_model(
            self._provider,
            prompt,
            system="You are a task planner. Return valid JSON only.",
            context=ModelCallContext(session_id=session_id, purpose="planning"),
        )
        try:
            return Plan.model_validate(json.loads(raw))
        except Exception:
            return Plan(
                tasks=[
                    Task(
                        id="t1",
                        title="Execute objective",
                        description=objective,
                        verification=[],
                    )
                ]
            )
