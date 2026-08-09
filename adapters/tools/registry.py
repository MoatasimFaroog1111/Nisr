from __future__ import annotations

import json
from typing import Any

from domain.models import ToolResult
from ports.audit import AuditPort
from ports.tool import ToolPort


class ToolRegistry:
    def __init__(self, audit: AuditPort | None = None):
        self._tools: dict[str, ToolPort] = {}
        self._audit = audit

    def register(self, tool: ToolPort) -> None:
        self._tools[tool.name] = tool

    async def call(
        self, name: str, arguments: dict[str, Any], *, session_id: str = ""
    ) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            result = ToolResult(ok=False, error=f"Unknown tool: {name}")
            if self._audit:
                self._audit.record("tool.unknown", session_id=session_id, data={"name": name})
            return result
        if self._audit:
            self._audit.record(
                "tool.start",
                session_id=session_id,
                data={"name": name, "arguments": arguments},
            )
        try:
            result = await tool.run(arguments)
        except Exception as exc:
            result = ToolResult(ok=False, error=f"Unhandled tool error: {exc}")
        if self._audit:
            self._audit.record(
                "tool.finish",
                session_id=session_id,
                data={
                    "name": name,
                    "ok": result.ok,
                    "error": result.error,
                    "metadata": result.metadata,
                    "output_preview": str(result.output)[:2000] if result.output is not None else None,
                },
            )
        return result

    def describe(self) -> str:
        return json.dumps(
            [tool.schema() for tool in self._tools.values()],
            ensure_ascii=False,
            indent=2,
        )

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)
