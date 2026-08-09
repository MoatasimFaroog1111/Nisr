from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.models import ToolResult


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}
