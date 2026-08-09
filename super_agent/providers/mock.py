from __future__ import annotations

from collections import deque
from super_agent.providers.base import ModelProvider


class MockProvider(ModelProvider):
    def __init__(self, responses: list[str]):
        self.responses = deque(responses)

    async def complete(self, prompt: str, system: str = "") -> str:
        if not self.responses:
            return '{"action":"finish","result":"done"}'
        return self.responses.popleft()
