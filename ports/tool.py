from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from domain.models import ToolResult


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    session_id: str = ""
    user_id: str = ""
    task_id: str = ""
    actor: str = "agent"


class ToolPort(Protocol):
    name: str
    description: str
    async def run(self, arguments: dict[str, Any]) -> ToolResult: ...
    def schema(self) -> dict[str, Any]: ...


class ContextualToolPort(Protocol):
    async def run_contextual(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult: ...


class ToolRegistryPort(Protocol):
    def register(self, tool: ToolPort) -> None: ...
    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str = "",
        user_id: str = "",
        task_id: str = "",
        actor: str = "agent",
    ) -> ToolResult: ...
    def sanitize(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
    def describe(self) -> str: ...
    @property
    def names(self) -> list[str]: ...
