from __future__ import annotations

from collections import deque

from ports.model_provider import ModelCallContext


class MockModelAdapter:
    def __init__(self, responses: list[str]):
        self._responses = deque(responses)

    async def complete(
        self,
        prompt: str,
        system: str = "",
        *,
        context: ModelCallContext | None = None,
    ) -> str:
        if not self._responses:
            return '{"action":"finish","result":"done"}'
        return self._responses.popleft()
